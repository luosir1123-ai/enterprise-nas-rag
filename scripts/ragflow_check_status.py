"""Check RAGFlow dataset and document parsing status.

Run inside the RAGFlow container with /ragflow as the working directory.
This script is ASCII-only; Chinese dataset names are represented with
Unicode escapes to avoid terminal encoding issues.
"""

from __future__ import annotations

import json
from datetime import datetime

from api.db.services.document_service import DocumentService
from api.db.services.knowledgebase_service import KnowledgebaseService
from ragflow_env import get_target_tenant


DATASET_NAMES = [
    "\u91c7\u8d2d\u77e5\u8bc6\u5e93",
    "\u9500\u552e\u77e5\u8bc6\u5e93",
    "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u8bc6\u5e93",
]

RUN_STATUS = {
    "0": "UNSTART",
    "1": "RUNNING",
    "2": "CANCEL",
    "3": "DONE",
    "4": "FAIL",
}


def main() -> None:
    tenant = get_target_tenant()
    result = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "tenant_llm_id": tenant.llm_id,
        "tenant_embd_id": tenant.embd_id,
        "datasets": [],
    }
    for name in DATASET_NAMES:
        ok, kb = KnowledgebaseService.get_by_name(name, tenant.id)
        if not ok:
            result["datasets"].append({"name": name, "missing": True})
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
                    "progress_msg_tail": (doc.progress_msg or "")[-500:],
                }
            )
        result["datasets"].append(
            {
                "id": kb.id,
                "name": kb.name,
                "parser_id": kb.parser_id,
                "embd_id": kb.embd_id,
                "doc_num": int(kb.doc_num or 0),
                "chunk_num": int(kb.chunk_num or 0),
                "token_num": int(kb.token_num or 0),
                "documents": docs,
            }
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
