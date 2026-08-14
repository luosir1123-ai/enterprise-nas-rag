"""Import the first NAS sample batch into RAGFlow.

Run this script inside the RAGFlow container with /ragflow as the working
directory. The file is intentionally ASCII-only; Chinese names are built with
Unicode escapes so Windows -> SSH -> Docker transfer cannot corrupt them.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from api.apps.services import dataset_api_service
from api.db.services.document_service import DocumentService
from api.db.services.file_service import FileService
from api.db.services.knowledgebase_service import KnowledgebaseService
from common.constants import TaskStatus


TENANT_ID = "<configure-RAGFLOW_TENANT_ID>"
EMBD_ID = "bge-m3:latest@local-ollama@Ollama"
LLM_ID = "qwen3.6:27b@local-ollama@Ollama"
NAS_ROOT = Path("/ragflow/nas/LE_TOUCH_SHR")
REPORT_PATH = Path("/tmp/ragflow_import_samples_result.json")


ZH = {
    "purchase_kb": "\u91c7\u8d2d\u77e5\u8bc6\u5e93",
    "sales_kb": "\u9500\u552e\u77e5\u8bc6\u5e93",
    "design_kb": "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u8bc6\u5e93",
    "purchase_desc": "\u4f9b\u5e94\u5546\u3001\u91c7\u8d2d\u6d41\u7a0b\u3001\u62a5\u4ef7\u3001\u5408\u540c\u3001\u7269\u6599\u8d44\u6599\u3002",
    "sales_desc": "\u5ba2\u6237\u8d44\u6599\u3001\u62a5\u4ef7\u65b9\u6848\u3001\u9500\u552e\u5408\u540c\u3001\u9879\u76ee\u8bb0\u5f55\u3002",
    "design_desc": "\u4ea7\u54c1\u65b9\u6848\u3001\u8bbe\u8ba1\u6587\u6863\u3001BOM\u3001\u8bc4\u5ba1\u6750\u6599\u3001\u6280\u672f\u8d44\u6599\u3002",
    "product_root": "\u4ea7\u54c1\u8bbe\u8ba1\u6210\u679c(2021\u5e74\u8d77)",
    "qa_factory": "QA+\u9a8c\u5382",
    "data_cable": "LT-C23 Find My\u6570\u636e\u7ebf",
    "watermark": "(\u6c34\u5370)Design Concept of Find My Cable.pdf",
    "charger_dir": "LT-G20 20W \u997c\u5e72 \u6c34\u8f6c\u5370 \u5355C\u5145\u7535\u5668",
    "quote_xlsx": "20W\u997c\u5e72\u8d85\u8584\u5145\u7535\u5668\u62a5\u4ef7\u5355.xlsx",
}


KNOWLEDGE_BASES = [
    {
        "key": "pur_shr",
        "name": ZH["purchase_kb"],
        "description": ZH["purchase_desc"],
        "root": "PUR-SHR",
    },
    {
        "key": "sales_shr",
        "name": ZH["sales_kb"],
        "description": ZH["sales_desc"],
        "root": "SALES-SHR",
    },
    {
        "key": "product_design",
        "name": ZH["design_kb"],
        "description": ZH["design_desc"],
        "root": ZH["product_root"],
    },
]


SAMPLES = {
    "sales_shr": [
        [
            "SALES-SHR",
            "Certificates",
            "LeTouch- 2024-2026 BEPI.pdf",
        ],
        [
            "SALES-SHR",
            "Certificates",
            "LeTouch- BEPI_level.pdf",
        ],
        [
            "SALES-SHR",
            ZH["qa_factory"],
            "107 LT - Sitecom Factory Audit Checklist -V1.3--for Factory-240701.docx",
        ],
    ],
    "product_design": [
        [
            ZH["product_root"],
            "Non-Disclosure Agreement.docx",
        ],
        [
            ZH["product_root"],
            ZH["data_cable"],
            ZH["watermark"],
        ],
        [
            ZH["product_root"],
            ZH["data_cable"],
            "Design Concept of Find My Cable.pdf",
        ],
        [
            ZH["product_root"],
            ZH["charger_dir"],
            ZH["quote_xlsx"],
        ],
    ],
}


class LocalUploadFile:
    def __init__(self, path: Path):
        self.path = path
        self.filename = path.name

    def read(self) -> bytes:
        with self.path.open("rb") as f:
            return f.read()


def parser_config() -> dict:
    return {
        "chunk_token_num": 512,
        "delimiter": "\n!?;.;!?",
        "layout_recognize": "Plain Text",
        "task_page_size": 12,
        "llm_id": LLM_ID,
    }


async def ensure_kb(kb_def: dict, report: dict):
    ok, kb = KnowledgebaseService.get_by_name(kb_def["name"], TENANT_ID)
    if ok:
        report["knowledge_bases"].append(
            {
                "key": kb_def["key"],
                "name": kb.name,
                "id": kb.id,
                "action": "reused",
                "doc_num": kb.doc_num,
                "chunk_num": kb.chunk_num,
            }
        )
        return kb

    req = {
        "name": kb_def["name"],
        "description": kb_def["description"],
        "embd_id": EMBD_ID,
        "parser_id": "naive",
        "permission": "me",
        "parser_config": parser_config(),
    }
    created, result = await dataset_api_service.create_dataset(TENANT_ID, req)
    if not created:
        raise RuntimeError(f"Failed to create dataset {kb_def['key']}: {result}")
    ok, kb = KnowledgebaseService.get_by_id(result["id"])
    if not ok:
        raise RuntimeError(f"Dataset created but cannot reload: {result}")
    report["knowledge_bases"].append(
        {
            "key": kb_def["key"],
            "name": kb.name,
            "id": kb.id,
            "action": "created",
            "doc_num": kb.doc_num,
            "chunk_num": kb.chunk_num,
        }
    )
    return kb


async def cleanup_garbled_kbs(report: dict) -> None:
    stale_ids = [
        "<configure-stale-kb-id-1>",
        "<configure-stale-kb-id-2>",
    ]
    existing = []
    for kb_id in stale_ids:
        ok, kb = KnowledgebaseService.get_by_id(kb_id)
        if ok and kb.tenant_id == TENANT_ID:
            existing.append(kb_id)
    if not existing:
        report["cleanup"] = {"deleted_ids": [], "message": "no stale garbled datasets found"}
        return
    ok, result = await dataset_api_service.delete_datasets(TENANT_ID, ids=existing)
    if not ok:
        report["cleanup"] = {"deleted_ids": [], "error": str(result)}
        raise RuntimeError(f"Failed to delete stale datasets: {result}")
    report["cleanup"] = {"deleted_ids": existing, "result": result}


def doc_exists(kb_id: str, filename: str):
    docs = DocumentService.query(kb_id=kb_id, name=filename)
    return docs[0] if docs else None


def queue_parse_if_needed(doc_obj, report: dict, source: str) -> None:
    ok, doc = DocumentService.get_by_id(doc_obj["id"] if isinstance(doc_obj, dict) else doc_obj.id)
    if not ok:
        report["queued"].append({"name": source, "status": "missing_after_upload"})
        return

    run = str(doc.run)
    chunk_num = int(doc.chunk_num or 0)
    if run == str(TaskStatus.DONE.value) and chunk_num > 0:
        report["queued"].append(
            {
                "id": doc.id,
                "name": doc.name,
                "status": "already_done",
                "chunk_num": chunk_num,
            }
        )
        return
    if run == str(TaskStatus.RUNNING.value):
        report["queued"].append(
            {
                "id": doc.id,
                "name": doc.name,
                "status": "already_running",
                "progress": float(doc.progress or 0),
            }
        )
        return

    DocumentService.run(TENANT_ID, doc.to_dict(), {})
    report["queued"].append(
        {
            "id": doc.id,
            "name": doc.name,
            "status": "queued",
            "previous_run": run,
        }
    )


def upload_samples(kb_map: dict, report: dict) -> None:
    for kb_key, rel_paths in SAMPLES.items():
        kb = kb_map[kb_key]
        for parts in rel_paths:
            src = NAS_ROOT.joinpath(*parts)
            item = {
                "knowledge_base": kb_key,
                "path": str(src),
                "filename": src.name,
            }
            if not src.exists():
                item["status"] = "missing"
                report["uploads"].append(item)
                continue
            if not src.is_file():
                item["status"] = "not_file"
                report["uploads"].append(item)
                continue

            existing_doc = doc_exists(kb.id, src.name)
            if existing_doc:
                item["status"] = "already_uploaded"
                item["document_id"] = existing_doc.id
                item["size"] = int(existing_doc.size or 0)
                report["uploads"].append(item)
                queue_parse_if_needed(existing_doc, report, str(src))
                continue

            upload_file = LocalUploadFile(src)
            parent_path = f"nas-first-batch/{kb_key}"
            errors, files = FileService.upload_document(
                kb,
                [upload_file],
                TENANT_ID,
                src="local",
                parent_path=parent_path,
            )
            if errors:
                item["status"] = "upload_error"
                item["errors"] = [str(e) for e in errors]
                report["uploads"].append(item)
                continue
            if not files:
                item["status"] = "upload_no_document"
                report["uploads"].append(item)
                continue

            doc, _blob = files[0]
            item["status"] = "uploaded"
            item["document_id"] = doc["id"] if isinstance(doc, dict) else doc.id
            item["size"] = int(src.stat().st_size)
            report["uploads"].append(item)
            queue_parse_if_needed(doc, report, str(src))


def collect_final_state(report: dict) -> None:
    final_kbs = []
    for kb_def in KNOWLEDGE_BASES:
        ok, kb = KnowledgebaseService.get_by_name(kb_def["name"], TENANT_ID)
        if ok:
            final_kbs.append(
                {
                    "key": kb_def["key"],
                    "id": kb.id,
                    "name": kb.name,
                    "doc_num": int(kb.doc_num or 0),
                    "chunk_num": int(kb.chunk_num or 0),
                    "token_num": int(kb.token_num or 0),
                    "parser_id": kb.parser_id,
                    "embd_id": kb.embd_id,
                }
            )
    report["final_knowledge_bases"] = final_kbs

    doc_rows = []
    for kb in final_kbs:
        docs = DocumentService.query(kb_id=kb["id"])
        for doc in docs:
            doc_rows.append(
                {
                    "kb_name": kb["name"],
                    "id": doc.id,
                    "name": doc.name,
                    "run": str(doc.run),
                    "progress": float(doc.progress or 0),
                    "chunk_num": int(doc.chunk_num or 0),
                    "token_num": int(doc.token_num or 0),
                    "size": int(doc.size or 0),
                }
            )
    report["documents"] = doc_rows


async def main() -> None:
    if not NAS_ROOT.exists():
        raise RuntimeError(f"NAS root is not mounted in container: {NAS_ROOT}")

    report = {
        "tenant_id": TENANT_ID,
        "nas_root": str(NAS_ROOT),
        "cleanup": {},
        "knowledge_bases": [],
        "uploads": [],
        "queued": [],
        "final_knowledge_bases": [],
        "documents": [],
    }

    await cleanup_garbled_kbs(report)
    kb_map = {}
    for kb_def in KNOWLEDGE_BASES:
        kb_map[kb_def["key"]] = await ensure_kb(kb_def, report)
    upload_samples(kb_map, report)
    collect_final_state(report)

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
