"""Diagnose the current RAGFlow chat app and retrieval state.

Run inside the RAGFlow container with /ragflow as the working directory.
This script is read-only: it does not update dialogs, datasets, or documents.
Chinese text is represented with Unicode escapes so PowerShell terminals do not
damage the source encoding.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from api.db.services.conversation_service import ConversationService
from api.db.services.dialog_service import DialogService
from api.db.services.document_service import DocumentService
from api.db.services.knowledgebase_service import KnowledgebaseService
from common import settings
from rag.nlp import search


TENANT_ID = "782dc11073c211f1a60c01b4967394e8"
CHAT_ID = "5dc6373c746011f1b4e439a2bb3fe40b"

DATASET_NAMES = [
    "\u91c7\u8d2d\u77e5\u8bc6\u5e93",
    "\u9500\u552e\u77e5\u8bc6\u5e93",
    "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u8bc6\u5e93",
]

TEST_QUERIES = [
    "LT-G20\u5927\u7406\u77f3 \u5355\u4ef7\u591a\u5c11\uff1f",
    "LT-G20\u5927\u7406\u77f3",
    "LT-G20",
    "\u5927\u7406\u77f3",
    "20W",
]

RUN_STATUS = {
    "0": "UNSTART",
    "1": "RUNNING",
    "2": "CANCEL",
    "3": "DONE",
    "4": "FAIL",
}


def _clip(text: str, limit: int = 700) -> str:
    return (text or "").replace("\r", " ").replace("\n", " ")[:limit]


def _safe_json(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


async def _search_query(dealer: search.Dealer, query: str, kb_ids: list[str]) -> dict:
    req = {
        "question": query,
        "kb_ids": kb_ids,
        "page": 1,
        "size": 8,
        "topk": 8,
        "similarity": 0.05,
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
        search.index_name(TENANT_ID),
        kb_ids,
        emb_mdl=None,
        highlight=False,
    )
    hits = []
    for chunk_id in result.ids[:8]:
        field = result.field.get(chunk_id, {})
        hits.append(
            {
                "chunk_id": chunk_id,
                "kb_id": field.get("kb_id", ""),
                "doc_id": field.get("doc_id", ""),
                "doc_name": field.get("docnm_kwd", ""),
                "page_num": field.get("page_num_int", []),
                "chunk_order": field.get("chunk_order_int"),
                "content_preview": _clip(field.get("content_with_weight", "")),
            }
        )
    return {"query": query, "total": int(result.total or 0), "hits": hits}


async def main() -> None:
    if settings.docStoreConn is None:
        settings.init_settings()

    ok, dialog = DialogService.get_by_id(CHAT_ID)
    if not ok:
        raise RuntimeError(f"Chat not found: {CHAT_ID}")

    datasets = []
    dataset_by_id = {}
    for name in DATASET_NAMES:
        kb_ok, kb = KnowledgebaseService.get_by_name(name, TENANT_ID)
        if not kb_ok:
            datasets.append({"name": name, "missing": True})
            continue

        docs = []
        for doc in DocumentService.query(kb_id=kb.id):
            run = str(doc.run)
            docs.append(
                {
                    "id": doc.id,
                    "name": doc.name,
                    "run": run,
                    "run_label": RUN_STATUS.get(run, run),
                    "progress": float(doc.progress or 0),
                    "chunk_num": int(doc.chunk_num or 0),
                    "token_num": int(doc.token_num or 0),
                    "size": int(doc.size or 0),
                    "progress_msg_tail": _clip(doc.progress_msg or "", 300),
                }
            )

        dataset = {
            "id": kb.id,
            "name": kb.name,
            "parser_id": kb.parser_id,
            "embd_id": kb.embd_id,
            "doc_num": int(kb.doc_num or 0),
            "chunk_num": int(kb.chunk_num or 0),
            "token_num": int(kb.token_num or 0),
            "documents": docs,
        }
        datasets.append(dataset)
        dataset_by_id[kb.id] = dataset

    conversations = []
    for conv in ConversationService.query(dialog_id=CHAT_ID):
        msg = conv.message or []
        conversations.append(
            {
                "id": conv.id,
                "name": conv.name,
                "message_count": len(msg),
                "last_messages": _safe_json(msg[-4:]),
            }
        )

    kb_ids = list(dialog.kb_ids or [])
    dealer = search.Dealer(settings.docStoreConn)
    retrieval = []
    if kb_ids:
        for query in TEST_QUERIES:
            retrieval.append(await _search_query(dealer, query, kb_ids))

    prompt_config = dialog.prompt_config or {}
    output = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tenant_id": TENANT_ID,
        "chat": {
            "id": dialog.id,
            "name": dialog.name,
            "kb_ids": kb_ids,
            "bound_dataset_names": [
                dataset_by_id.get(kb_id, {}).get("name", "<unknown>")
                for kb_id in kb_ids
            ],
            "llm_id": getattr(dialog, "llm_id", None),
            "llm_setting": dialog.llm_setting,
            "similarity_threshold": getattr(dialog, "similarity_threshold", None),
            "vector_similarity_weight": getattr(dialog, "vector_similarity_weight", None),
            "top_n": getattr(dialog, "top_n", None),
            "top_k": getattr(dialog, "top_k", None),
            "do_refer": getattr(dialog, "do_refer", None),
            "prompt_has_knowledge": "{knowledge}" in prompt_config.get("system", ""),
            "prompt_parameters": prompt_config.get("parameters", []),
        },
        "datasets": datasets,
        "conversations": conversations,
        "retrieval": retrieval,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
