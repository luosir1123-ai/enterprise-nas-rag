"""Cancel redundant RAGFlow parse jobs using document content hashes.

Run inside the RAGFlow container with /ragflow as the working directory.
The default mode is report-only. Set RAGFLOW_CANCEL_DUPLICATES_APPLY=1 to
cancel duplicate jobs. Documents and objects are kept; only redundant parse
tasks and their partial index entries are cancelled.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path


REPORT_PATH = Path(
    os.getenv(
        "RAGFLOW_CANCEL_DUPLICATES_REPORT_PATH",
        "/tmp/ragflow_cancel_duplicate_parses_report.json",
    )
)
APPLY = os.getenv("RAGFLOW_CANCEL_DUPLICATES_APPLY", "0").lower() in {
    "1",
    "true",
    "yes",
    "y",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sort_key(doc) -> tuple[int, str]:
    return int(doc.create_time or 0), str(doc.id)


def doc_snapshot(doc) -> dict:
    return {
        "document_id": doc.id,
        "name": doc.name,
        "run": str(doc.run),
        "chunk_num": int(doc.chunk_num or 0),
        "token_num": int(doc.token_num or 0),
        "progress": float(doc.progress or 0),
        "content_hash": doc.content_hash or "",
        "create_date": str(doc.create_date or ""),
    }


def main() -> None:
    from api.db.services.document_service import DocumentService
    from api.db.services.knowledgebase_service import KnowledgebaseService
    from api.db.services.task_service import cancel_all_task_of
    from common import settings
    from common.constants import TaskStatus
    from rag.nlp import search
    from ragflow_env import get_target_tenant

    settings.init_settings()
    tenant = get_target_tenant()
    report = {
        "started_at": now_text(),
        "finished_at": None,
        "apply": APPLY,
        "tenant_id": tenant.id,
        "duplicate_group_count": 0,
        "selected_count": 0,
        "cancelled_count": 0,
        "skipped_count": 0,
        "groups": [],
        "errors": [],
    }

    for kb in KnowledgebaseService.query(tenant_id=tenant.id):
        docs = list(DocumentService.query(kb_id=kb.id))
        by_hash = defaultdict(list)
        for doc in docs:
            if doc.content_hash:
                by_hash[doc.content_hash].append(doc)

        for content_hash, group_docs in by_hash.items():
            running = sorted(
                (doc for doc in group_docs if str(doc.run) == TaskStatus.RUNNING.value),
                key=sort_key,
            )
            if not running or len(group_docs) < 2:
                continue

            done = sorted(
                (doc for doc in group_docs if str(doc.run) == TaskStatus.DONE.value),
                key=sort_key,
            )
            if done:
                keeper = done[0]
                selected = running
                reason = "same_hash_as_completed_document"
            elif len(running) > 1:
                keeper = running[0]
                selected = running[1:]
                reason = "same_hash_as_earlier_running_document"
            else:
                continue

            group_report = {
                "knowledge_base": kb.name,
                "knowledge_base_id": kb.id,
                "content_hash": content_hash,
                "reason": reason,
                "keeper": doc_snapshot(keeper),
                "selected": [doc_snapshot(doc) for doc in selected],
                "cancelled": [],
                "skipped": [],
            }
            report["duplicate_group_count"] += 1
            report["selected_count"] += len(selected)

            if APPLY:
                for selected_doc in selected:
                    try:
                        ok, fresh = DocumentService.get_by_id(selected_doc.id)
                        if not ok or str(fresh.run) != TaskStatus.RUNNING.value:
                            group_report["skipped"].append(
                                {
                                    "document_id": selected_doc.id,
                                    "reason": "no_longer_running",
                                }
                            )
                            report["skipped_count"] += 1
                            continue

                        cancel_all_task_of(fresh.id)
                        DocumentService.update_by_id(
                            fresh.id,
                            {
                                "run": TaskStatus.CANCEL.value,
                                "progress": 0,
                                "chunk_num": 0,
                            },
                        )
                        index_name = search.index_name(tenant.id)
                        if settings.docStoreConn.index_exist(index_name, fresh.kb_id):
                            settings.docStoreConn.delete(
                                {"doc_id": fresh.id}, index_name, fresh.kb_id
                            )
                        group_report["cancelled"].append(doc_snapshot(fresh))
                        report["cancelled_count"] += 1
                    except Exception as exc:
                        report["errors"].append(
                            {
                                "document_id": selected_doc.id,
                                "name": selected_doc.name,
                                "error": repr(exc),
                            }
                        )

            report["groups"].append(group_report)

    report["finished_at"] = now_text()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "groups"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
