"""Run a minimal retrieval smoke test against RAGFlow chunks.

Run inside the RAGFlow container with /ragflow as the working directory.
This checks retrieval only, not final LLM answering.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from api.db.services.knowledgebase_service import KnowledgebaseService
from common import settings
from rag.nlp import search
from ragflow_env import get_target_tenant_id


REPORT_PATH = Path("/tmp/ragflow_retrieval_smoke_report.json")

DATASETS = {
    "purchase": "\u91c7\u8d2d\u77e5\u8bc6\u5e93",
    "sales_shr": "\u9500\u552e\u77e5\u8bc6\u5e93",
    "product_design": "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u8bc6\u5e93",
}

TESTS = [
    {
        "dataset_key": "purchase",
        "question": "ISO9001",
        "expected_file_hint": "ISO9001",
    },
    {
        "dataset_key": "purchase",
        "question": "CBATB5005",
        "expected_file_hint": "CBATB5005",
    },
    {
        "dataset_key": "sales_shr",
        "question": "BEPI",
        "expected_file_hint": "LeTouch-",
    },
    {
        "dataset_key": "sales_shr",
        "question": "BSCI",
        "expected_file_hint": "BSCI",
    },
    {
        "dataset_key": "product_design",
        "question": "Find My Cable",
        "expected_file_hint": "Find My Cable",
    },
    {
        "dataset_key": "product_design",
        "question": "20W",
        "expected_file_hint": "20W",
    },
]


def _clip(text: str, limit: int = 500) -> str:
    text = (text or "").replace("\r", " ").replace("\n", " ")
    return text[:limit]


async def run_test(dealer: search.Dealer, dataset_key: str, question: str, kb_id: str, tenant_id: str) -> dict:
    req = {
        "question": question,
        "kb_ids": [kb_id],
        "page": 1,
        "size": 5,
        "topk": 5,
        "similarity": 0.1,
        "fields": [
            "docnm_kwd",
            "content_with_weight",
            "kb_id",
            "doc_id",
            "page_num_int",
            "chunk_order_int",
        ],
    }
    result = await dealer.search(
        req,
        search.index_name(tenant_id),
        [kb_id],
        emb_mdl=None,
        highlight=False,
    )
    hits = []
    for chunk_id in result.ids[:5]:
        field = result.field.get(chunk_id, {})
        hits.append(
            {
                "chunk_id": chunk_id,
                "doc_name": field.get("docnm_kwd", ""),
                "doc_id": field.get("doc_id", ""),
                "page_num": field.get("page_num_int", []),
                "chunk_order": field.get("chunk_order_int"),
                "content_preview": _clip(field.get("content_with_weight", "")),
            }
        )
    return {
        "dataset_key": dataset_key,
        "question": question,
        "total": int(result.total or 0),
        "hits": hits,
    }


async def main() -> None:
    if settings.docStoreConn is None:
        settings.init_settings()

    tenant_id = get_target_tenant_id()
    kb_by_key = {}
    for key, name in DATASETS.items():
        ok, kb = KnowledgebaseService.get_by_name(name, tenant_id)
        if ok:
            kb_by_key[key] = kb

    dealer = search.Dealer(settings.docStoreConn)
    output = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tenant_id": tenant_id,
        "index_name": search.index_name(tenant_id),
        "datasets": {
            key: {
                "id": kb.id,
                "name": kb.name,
                "doc_num": int(kb.doc_num or 0),
                "chunk_num": int(kb.chunk_num or 0),
                "token_num": int(kb.token_num or 0),
            }
            for key, kb in kb_by_key.items()
        },
        "tests": [],
    }
    for test in TESTS:
        kb = kb_by_key.get(test["dataset_key"])
        if not kb:
            output["tests"].append({**test, "error": "dataset_missing"})
            continue
        res = await run_test(dealer, test["dataset_key"], test["question"], kb.id, tenant_id)
        expected = test["expected_file_hint"].lower()
        res["matched_expected_hint"] = any(expected in hit["doc_name"].lower() for hit in res["hits"])
        res["expected_file_hint"] = test["expected_file_hint"]
        output["tests"].append(res)

    REPORT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
