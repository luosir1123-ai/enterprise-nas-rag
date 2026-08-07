"""Queue a small batch of already-uploaded RAGFlow documents for parsing.

Run inside the RAGFlow container with `/ragflow` as working directory.

Usage examples:
  python /tmp/ragflow_queue_unparsed_batch.py
  RAGFLOW_PARSE_LIMIT_PER_KB=5 python /tmp/ragflow_queue_unparsed_batch.py

This script does not read or modify NAS files. It only triggers RAGFlow parsing
for documents that already exist in RAGFlow storage.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from api.db.services.document_service import DocumentService
from api.db.services.file2document_service import File2DocumentService
from api.db.services.knowledgebase_service import KnowledgebaseService
from common import settings
from common.constants import TaskStatus
from ragflow_env import get_target_tenant_id


REPORT_PATH = Path("/tmp/ragflow_queue_unparsed_batch_report.json")
LIMIT_PER_KB = int(os.getenv("RAGFLOW_PARSE_LIMIT_PER_KB", "5"))
MAX_BYTES = int(os.getenv("RAGFLOW_PARSE_MAX_BYTES", str(50 * 1024 * 1024)))
TARGET_KB_KEYS = {
    item.strip()
    for item in os.getenv("RAGFLOW_PARSE_KB_KEYS", "purchase,sales,product_design").split(",")
    if item.strip()
}

KBS = {
    "purchase": "\u91c7\u8d2d\u77e5\u8bc6\u5e93",
    "sales": "\u9500\u552e\u77e5\u8bc6\u5e93",
    "product_design": "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u8bc6\u5e93",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def storage_exists(doc) -> bool:
    try:
        bucket, name = File2DocumentService.get_storage_address(doc_id=doc.id)
        return bool(settings.STORAGE_IMPL.obj_exist(bucket, name))
    except Exception:
        try:
            return bool(settings.STORAGE_IMPL.obj_exist(doc.kb_id, doc.location))
        except Exception:
            return False


def queue_kb(kb_key: str, kb_name: str, report: dict) -> None:
    tenant_id = get_target_tenant_id()
    ok, kb = KnowledgebaseService.get_by_name(kb_name, tenant_id)
    if not ok:
        report["errors"].append({"kb_key": kb_key, "stage": "load_kb", "error": "dataset_not_found"})
        return

    queued = 0
    skipped = 0
    for doc in DocumentService.query(kb_id=kb.id):
        run = str(doc.run)
        chunk_num = int(doc.chunk_num or 0)
        if run in {str(TaskStatus.DONE.value), str(TaskStatus.RUNNING.value)}:
            skipped += 1
            continue
        if run == str(TaskStatus.FAIL.value) and chunk_num > 0:
            skipped += 1
            report["files"].append(
                {
                    "kb_key": kb_key,
                    "knowledge_base": kb.name,
                    "document_id": doc.id,
                    "name": doc.name,
                    "previous_run": run,
                    "chunk_num": chunk_num,
                    "status": "\u8df3\u8fc7\uff1a\u72b6\u6001\u5931\u8d25\u4f46\u5df2\u6709\u5207\u7247\uff0c\u7559\u5f85\u5355\u72ec\u590d\u6838",
                }
            )
            continue
        item = {
            "kb_key": kb_key,
            "knowledge_base": kb.name,
            "document_id": doc.id,
            "name": doc.name,
            "previous_run": run,
            "chunk_num": chunk_num,
        }
        if not storage_exists(doc):
            item["status"] = "\u8df3\u8fc7\uff1a\u5bf9\u8c61\u5b58\u50a8\u6587\u4ef6\u4e0d\u5b58\u5728"
            report["files"].append(item)
            skipped += 1
            continue
        size = int(doc.size or 0)
        item["size"] = size
        if MAX_BYTES > 0 and size > MAX_BYTES:
            item["status"] = f"\u8df3\u8fc7\uff1a\u8d85\u8fc7\u672c\u8f6e\u89e3\u6790\u5927\u5c0f\u4e0a\u9650 {MAX_BYTES}"
            report["files"].append(item)
            skipped += 1
            continue
        if queued >= LIMIT_PER_KB:
            item["status"] = "\u8df3\u8fc7\uff1a\u8fbe\u5230\u672c\u77e5\u8bc6\u5e93\u89e3\u6790\u4e0a\u9650"
            report["files"].append(item)
            skipped += 1
            continue
        try:
            DocumentService.run(tenant_id, doc.to_dict(), {})
            item["status"] = "\u5df2\u89e6\u53d1\u89e3\u6790"
            queued += 1
        except Exception as exc:
            item["status"] = "\u89e6\u53d1\u89e3\u6790\u5931\u8d25"
            item["error"] = repr(exc)
            report["errors"].append({"stage": "queue_parse", **item})
        report["files"].append(item)

    report["datasets"].append(
        {
            "kb_key": kb_key,
            "id": kb.id,
            "name": kb.name,
            "queued": queued,
            "skipped": skipped,
            "doc_num": int(kb.doc_num or 0),
            "chunk_num": int(kb.chunk_num or 0),
        }
    )


def main() -> None:
    settings.init_settings()
    report = {
        "started_at": now_text(),
        "tenant_id": get_target_tenant_id(),
        "limit_per_kb": LIMIT_PER_KB,
        "max_bytes": MAX_BYTES,
        "target_kb_keys": sorted(TARGET_KB_KEYS),
        "datasets": [],
        "files": [],
        "errors": [],
        "finished_at": None,
    }

    for kb_key, kb_name in KBS.items():
        if kb_key in TARGET_KB_KEYS:
            queue_kb(kb_key, kb_name, report)

    report["finished_at"] = now_text()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
