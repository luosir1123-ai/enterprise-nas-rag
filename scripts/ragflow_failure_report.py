"""Export and classify failed RAGFlow documents.

Run inside the RAGFlow container with /ragflow as the working directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


DATASETS = {
    "purchase": "\u91c7\u8d2d\u77e5\u8bc6\u5e93",
    "sales": "\u9500\u552e\u77e5\u8bc6\u5e93",
}

CLASSIFIERS = (
    (
        "embedding_api_or_network",
        re.compile(
            r"embedding|dashscope|arrearage|api.?key|connection|connecterror|"
            r"dns|resolve|timed?\s*out|timeout|429|rate.?limit|quota",
            re.IGNORECASE,
        ),
    ),
    (
        "ocr_or_image",
        re.compile(
            r"ocr|opencv|cv2|remap|image|pixel|layout recognition",
            re.IGNORECASE,
        ),
    ),
    (
        "file_format_or_corruption",
        re.compile(
            r"corrupt|damaged|password|encrypted|unsupported|invalid file|"
            r"libreoffice|tika|zipfile|badzipfile|cannot open|failed to open",
            re.IGNORECASE,
        ),
    ),
    (
        "parser_or_runtime",
        re.compile(
            r"traceback|exception|memoryerror|out of memory|killed|parser|"
            r"assertionerror|typeerror|valueerror|keyerror|indexerror",
            re.IGNORECASE,
        ),
    ),
)


def classify_failure(message: str) -> str:
    for label, pattern in CLASSIFIERS:
        if pattern.search(message or ""):
            return label
    return "unknown"


def compact_message(message: str, limit: int = 1000) -> str:
    lines = [line.strip() for line in (message or "").splitlines() if line.strip()]
    errors = [line for line in lines if "error" in line.lower() or "fail" in line.lower()]
    selected = errors[-3:] if errors else lines[-5:]
    return " | ".join(selected)[-limit:]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--csv-output", required=True)
    return parser.parse_args()


def main() -> None:
    from api.db.services.document_service import DocumentService
    from api.db.services.knowledgebase_service import KnowledgebaseService
    from ragflow_env import get_target_tenant

    args = parse_args()
    tenant = get_target_tenant()
    rows = []

    for key, name in DATASETS.items():
        ok, kb = KnowledgebaseService.get_by_name(name, tenant.id)
        if not ok:
            raise RuntimeError(f"dataset not found: {name}")

        for doc in DocumentService.query(kb_id=kb.id):
            if str(doc.run) != "4":
                continue
            message = doc.progress_msg or ""
            chunk_num = int(doc.chunk_num or 0)
            rows.append(
                {
                    "knowledge_base_key": key,
                    "knowledge_base": name,
                    "knowledge_base_id": kb.id,
                    "document_id": doc.id,
                    "document_name": doc.name,
                    "suffix": doc.suffix,
                    "size_bytes": int(doc.size or 0),
                    "chunk_num": chunk_num,
                    "token_num": int(doc.token_num or 0),
                    "failure_scope": "partial_with_chunks" if chunk_num else "zero_chunks",
                    "failure_category": classify_failure(message),
                    "recommended_action": (
                        "review_retrieval_before_retry"
                        if chunk_num
                        else "retry_after_fix"
                    ),
                    "message_summary": compact_message(message),
                }
            )

    rows.sort(
        key=lambda row: (
            row["knowledge_base_key"],
            row["failure_scope"],
            row["failure_category"],
            row["document_name"],
        )
    )
    category_counts = Counter(row["failure_category"] for row in rows)
    scope_counts = Counter(row["failure_scope"] for row in rows)
    dataset_counts = Counter(row["knowledge_base_key"] for row in rows)
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tenant_id": tenant.id,
        "failed_document_count": len(rows),
        "counts_by_dataset": dict(sorted(dataset_counts.items())),
        "counts_by_scope": dict(sorted(scope_counts.items())),
        "counts_by_category": dict(sorted(category_counts.items())),
        "documents": rows,
    }

    json_path = Path(args.json_output)
    csv_path = Path(args.csv_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = list(rows[0]) if rows else [
        "knowledge_base_key",
        "knowledge_base",
        "knowledge_base_id",
        "document_id",
        "document_name",
        "suffix",
        "size_bytes",
        "chunk_num",
        "token_num",
        "failure_scope",
        "failure_category",
        "recommended_action",
        "message_summary",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({key: value for key, value in report.items() if key != "documents"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
