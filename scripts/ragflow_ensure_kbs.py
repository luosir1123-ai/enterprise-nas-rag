"""Ensure the three enterprise NAS datasets exist in the current RAGFlow tenant.

Run inside the RAGFlow container with `/ragflow` as working directory.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from api.db.services.knowledgebase_service import KnowledgebaseService
from api.utils.api_utils import verify_embedding_availability
from common import settings
from common.constants import StatusEnum

from ragflow_env import get_target_tenant


REPORT_PATH = Path("/tmp/ragflow_ensure_kbs_report.json")

KBS = [
    {
        "key": "purchase",
        "name": "\u91c7\u8d2d\u77e5\u8bc6\u5e93",
        "description": "\u4f9b\u5e94\u5546\u3001\u91c7\u8d2d\u6d41\u7a0b\u3001\u62a5\u4ef7\u3001\u5408\u540c\u3001\u7269\u6599\u8d44\u6599\u3002",
    },
    {
        "key": "sales",
        "name": "\u9500\u552e\u77e5\u8bc6\u5e93",
        "description": "\u5ba2\u6237\u8d44\u6599\u3001\u62a5\u4ef7\u65b9\u6848\u3001\u9500\u552e\u5408\u540c\u3001\u9879\u76ee\u8bb0\u5f55\u3002",
    },
    {
        "key": "product_design",
        "name": "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u8bc6\u5e93",
        "description": "\u4ea7\u54c1\u65b9\u6848\u3001\u8bbe\u8ba1\u6587\u6863\u3001BOM\u3001\u8bc4\u5ba1\u6750\u6599\u3001\u6280\u672f\u8d44\u6599\u3002",
    },
]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_one(tenant, item: dict) -> dict:
    ok, kb = KnowledgebaseService.get_by_name(item["name"], tenant.id)
    if ok:
        return {
            "key": item["key"],
            "name": kb.name,
            "id": kb.id,
            "status": "exists",
            "embd_id": kb.embd_id,
            "parser_id": kb.parser_id,
            "doc_num": int(kb.doc_num or 0),
            "chunk_num": int(kb.chunk_num or 0),
        }

    embd_id = tenant.embd_id
    if not embd_id:
        raise RuntimeError("tenant default embedding model is not set")
    available, err = verify_embedding_availability(embd_id, tenant.id)
    if not available:
        raise RuntimeError(f"tenant default embedding is unavailable: {err}")

    ok, payload = KnowledgebaseService.create_with_name(
        name=item["name"],
        tenant_id=tenant.id,
        parser_id="naive",
        description=item["description"],
        language="Chinese",
        permission="me",
        embd_id=embd_id,
        status=StatusEnum.VALID.value,
    )
    if not ok:
        raise RuntimeError(str(payload))
    KnowledgebaseService.save(**payload)

    ok, kb = KnowledgebaseService.get_by_id(payload["id"])
    if not ok:
        raise RuntimeError(f"dataset created but not readable: {item['name']}")
    return {
        "key": item["key"],
        "name": kb.name,
        "id": kb.id,
        "status": "created",
        "embd_id": kb.embd_id,
        "parser_id": kb.parser_id,
        "doc_num": int(kb.doc_num or 0),
        "chunk_num": int(kb.chunk_num or 0),
    }


def main() -> None:
    if settings.docStoreConn is None:
        settings.init_settings()

    tenant = get_target_tenant()
    report = {
        "checked_at": now_text(),
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "tenant_llm_id": tenant.llm_id,
        "tenant_embd_id": tenant.embd_id,
        "datasets": [],
    }
    for item in KBS:
        report["datasets"].append(ensure_one(tenant, item))

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
