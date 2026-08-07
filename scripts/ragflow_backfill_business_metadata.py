"""Backfill deterministic business metadata without reparsing documents."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from api.db.services.doc_metadata_service import DocMetadataService
from api.db.services.document_service import DocumentService
from api.db.services.knowledgebase_service import KnowledgebaseService
from business_metadata import infer_business_metadata
from common import settings
from ragflow_env import get_target_tenant_id


OUT_PATH = Path(os.getenv("RAGFLOW_BUSINESS_METADATA_REPORT_PATH", "/tmp/ragflow_business_metadata_report.json"))
DRY_RUN = os.getenv("RAGFLOW_BUSINESS_METADATA_DRY_RUN", "1").lower() in {"1", "true", "yes", "y"}
BATCH_SIZE = int(os.getenv("RAGFLOW_BUSINESS_METADATA_BATCH_SIZE", "500"))
KB_NAMES = {
    "purchase": "\u91c7\u8d2d\u77e5\u8bc6\u5e93",
    "sales": "\u9500\u552e\u77e5\u8bc6\u5e93",
    "product_design": "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u8bc6\u5e93",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main() -> None:
    settings.init_settings()
    tenant_id = get_target_tenant_id()
    index_name = DocMetadataService._get_doc_meta_index_name(tenant_id)
    report = {
        "started_at": now_text(),
        "finished_at": None,
        "dry_run": DRY_RUN,
        "updated": 0,
        "errors": [],
        "datasets": [],
        "samples": [],
    }

    for kb_key, kb_name in KB_NAMES.items():
        ok, kb = KnowledgebaseService.get_by_name(kb_name, tenant_id)
        if not ok:
            report["errors"].append({"knowledge_base": kb_name, "error": "dataset_not_found"})
            continue
        documents = DocumentService.query(kb_id=kb.id, status="1")
        metadata_by_doc = DocMetadataService.get_metadata_for_documents(None, kb.id) or {}
        rows = []
        for document in documents:
            existing = dict(metadata_by_doc.get(document.id, {}) or {})
            source_path = str(existing.get("nas_relative_path") or document.location or document.name or "")
            inferred = infer_business_metadata(source_path, kb_key=kb_key)
            merged = {**existing, **inferred}
            rows.append({"id": document.id, "kb_id": kb.id, "meta_fields": merged})
            if len(report["samples"]) < 12:
                report["samples"].append(
                    {"document_id": document.id, "name": document.name, "inferred": inferred}
                )

        dataset_result = {"key": kb_key, "name": kb_name, "documents": len(rows), "updated": 0}
        if DRY_RUN:
            dataset_result["updated"] = len(rows)
            report["updated"] += len(rows)
        else:
            for start in range(0, len(rows), BATCH_SIZE):
                batch = rows[start : start + BATCH_SIZE]
                errors = settings.docStoreConn.insert(batch, index_name, kb.id)
                if errors:
                    report["errors"].append(
                        {"knowledge_base": kb_name, "start": start, "errors": errors[:20]}
                    )
                    continue
                dataset_result["updated"] += len(batch)
                report["updated"] += len(batch)
        report["datasets"].append(dataset_result)
        OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if not DRY_RUN:
        refresh_idx = getattr(settings.docStoreConn, "refresh_idx", None)
        if callable(refresh_idx):
            refresh_idx(index_name)
    report["finished_at"] = now_text()
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
