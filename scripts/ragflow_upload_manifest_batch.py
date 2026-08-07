"""Upload a precomputed manifest of NAS files into RAGFlow.

Run inside the RAGFlow container with `/ragflow` as working directory.

The manifest is a UTF-8 text file with one absolute NAS path per line. This
keeps slow NAS scanning separate from RAGFlow upload and parse triggering.
"""

from __future__ import annotations

import json
import os
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from api.db.services.document_service import DocumentService
from api.db.services.file2document_service import File2DocumentService
from api.db.services.file_service import FileService
from api.db.services.knowledgebase_service import KnowledgebaseService
from common import settings
from common.constants import TaskStatus
from ragflow_env import get_target_tenant_id


MANIFEST_PATH = Path("/tmp/ragflow_upload_manifest.txt")
REPORT_PATH = Path("/tmp/ragflow_upload_manifest_report.json")
LOG_PATH = Path("/tmp/ragflow_upload_manifest.log")
NAS_ROOT = Path("/ragflow/nas/LE_TOUCH_SHR")
MAX_BYTES = int(os.getenv("RAGFLOW_UPLOAD_MAX_BYTES", str(8 * 1024 * 1024)))
PARSE_AFTER_UPLOAD = os.getenv("RAGFLOW_PARSE_AFTER_UPLOAD", "0").lower() in {"1", "true", "yes", "y"}

KB_RULES = [
    ("purchase", "\u91c7\u8d2d\u77e5\u8bc6\u5e93", NAS_ROOT / "PUR-SHR"),
    ("sales", "\u9500\u552e\u77e5\u8bc6\u5e93", NAS_ROOT / "SALES-SHR"),
    ("product_design", "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u8bc6\u5e93", NAS_ROOT / "\u4ea7\u54c1\u8bbe\u8ba1\u6210\u679c(2021\u5e74\u8d77)"),
]


class LocalUploadFile:
    def __init__(self, path: Path):
        self.path = path
        self.filename = path.name

    def read(self) -> bytes:
        return self.path.read_bytes()


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    line = f"[{now_text()}] {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_report(report: dict) -> None:
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def norm_name(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def get_kb(name: str):
    ok, kb = KnowledgebaseService.get_by_name(name, get_target_tenant_id())
    if not ok:
        raise RuntimeError(f"dataset not found: {name}")
    return kb


def classify_path(path: Path):
    for kb_key, kb_name, root in KB_RULES:
        try:
            path.relative_to(root)
            return kb_key, kb_name, root
        except ValueError:
            pass
    return None, None, None


def doc_by_name(kb_id: str, filename: str):
    docs = DocumentService.query(kb_id=kb_id, name=filename)
    if docs:
        return docs[0]
    normalized = norm_name(filename)
    for doc in DocumentService.query(kb_id=kb_id):
        if norm_name(doc.name) == normalized:
            return doc
    return None


def storage_exists(doc) -> bool:
    try:
        bucket, name = File2DocumentService.get_storage_address(doc_id=doc.id)
        return bool(settings.STORAGE_IMPL.obj_exist(bucket, name))
    except Exception:
        try:
            return bool(settings.STORAGE_IMPL.obj_exist(doc.kb_id, doc.location))
        except Exception:
            return False


def remove_bad_doc(doc, report: dict) -> None:
    try:
        DocumentService.remove_document(doc, get_target_tenant_id())
        report["removed_bad_documents"].append(
            {
                "document_id": doc.id,
                "name": doc.name,
                "reason": "\u5bf9\u8c61\u5b58\u50a8\u6587\u4ef6\u4e0d\u5b58\u5728\uff0c\u6e05\u7406 RAGFlow \u574f\u8bb0\u5f55\u540e\u91cd\u4f20",
            }
        )
    except Exception as exc:
        report["errors"].append(
            {"stage": "remove_bad_doc", "document_id": doc.id, "name": doc.name, "error": repr(exc)}
        )


def queue_parse(doc, report: dict) -> str:
    ok, fresh = DocumentService.get_by_id(doc["id"] if isinstance(doc, dict) else doc.id)
    if not ok:
        return "\u6587\u6863\u8bb0\u5f55\u4e0d\u5b58\u5728"
    if not storage_exists(fresh):
        return "\u5bf9\u8c61\u5b58\u50a8\u6587\u4ef6\u4e0d\u5b58\u5728\uff0c\u672a\u89e6\u53d1\u89e3\u6790"
    run = str(fresh.run)
    chunk_num = int(fresh.chunk_num or 0)
    if run == str(TaskStatus.DONE.value) and chunk_num > 0:
        return "\u5df2\u89e3\u6790"
    if run == str(TaskStatus.RUNNING.value):
        return "\u89e3\u6790\u4e2d"
    try:
        DocumentService.run(get_target_tenant_id(), fresh.to_dict(), {})
        report["queued"].append({"document_id": fresh.id, "name": fresh.name})
        return "\u5df2\u89e6\u53d1\u89e3\u6790"
    except Exception as exc:
        report["errors"].append(
            {"stage": "queue_parse", "document_id": fresh.id, "name": fresh.name, "error": repr(exc)}
        )
        return f"queue_parse_failed: {exc!r}"


def safe_parent_path(kb_key: str, batch_name: str) -> str:
    return f"nas-manifest/{batch_name}/{kb_key}"


def load_manifest() -> list[Path]:
    paths: list[Path] = []
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            paths.append(Path(line))
    # Preserve order but deduplicate.
    seen = set()
    result = []
    for p in paths:
        if str(p) not in seen:
            seen.add(str(p))
            result.append(p)
    return result


def collect_state(report: dict) -> None:
    datasets = []
    for kb_key, kb_name, _root in KB_RULES:
        kb = get_kb(kb_name)
        docs = []
        for doc in DocumentService.query(kb_id=kb.id):
            docs.append(
                {
                    "id": doc.id,
                    "name": doc.name,
                    "run": str(doc.run),
                    "progress": float(doc.progress or 0),
                    "chunk_num": int(doc.chunk_num or 0),
                    "token_num": int(doc.token_num or 0),
                    "size": int(doc.size or 0),
                    "storage_exists": storage_exists(doc),
                    "progress_msg_tail": (doc.progress_msg or "")[-300:],
                }
            )
        datasets.append(
            {
                "kb_key": kb_key,
                "id": kb.id,
                "name": kb.name,
                "doc_num": int(kb.doc_num or 0),
                "chunk_num": int(kb.chunk_num or 0),
                "token_num": int(kb.token_num or 0),
                "documents": docs,
            }
        )
    report["final_state"] = datasets


def upload_path(path: Path, report: dict, batch_name: str) -> None:
    kb_key, kb_name, kb_root = classify_path(path)
    item = {
        "nas_path": str(path),
        "filename": path.name,
        "kb_key": kb_key,
        "knowledge_base": kb_name,
    }
    if not kb_key or not kb_name or not kb_root:
        item["status"] = "\u65e0\u6cd5\u5206\u7c7b\u5230\u4e09\u4e2a\u77e5\u8bc6\u5e93"
        report["errors"].append({"stage": "classify", **item})
        report["files"].append(item)
        write_report(report)
        return
    if not path.exists() or not path.is_file():
        item["status"] = "\u6587\u4ef6\u4e0d\u5b58\u5728"
        report["errors"].append({"stage": "missing_file", **item})
        report["files"].append(item)
        write_report(report)
        return

    size = path.stat().st_size
    item["size"] = size
    item["relative_path"] = str(path.relative_to(kb_root))
    if size <= 0:
        item["status"] = "\u7a7a\u6587\u4ef6"
        report["files"].append(item)
        write_report(report)
        return
    if MAX_BYTES > 0 and size > MAX_BYTES:
        item["status"] = "\u8d85\u8fc7\u5355\u6587\u4ef6\u9650\u5236"
        report["files"].append(item)
        write_report(report)
        return

    kb = get_kb(kb_name)
    started = time.time()
    log(f"upload start {kb_key}: {path.name}")

    existing = doc_by_name(kb.id, path.name)
    if existing:
        if not storage_exists(existing):
            remove_bad_doc(existing, report)
        else:
            item["status"] = "\u5df2\u5b58\u5728"
            item["document_id"] = existing.id
            if PARSE_AFTER_UPLOAD:
                item["parse_status"] = queue_parse(existing, report)
            else:
                item["parse_status"] = "\u4ec5\u4e0a\u4f20\uff0c\u672a\u89e6\u53d1\u89e3\u6790"
            report["files"].append(item)
            write_report(report)
            log(f"already exists {kb_key}: {path.name} -> {item['parse_status']}")
            return

    try:
        errors, files = FileService.upload_document(
            kb,
            [LocalUploadFile(path)],
            get_target_tenant_id(),
            src="local",
            parent_path=safe_parent_path(kb_key, batch_name),
        )
        item["upload_seconds"] = round(time.time() - started, 3)
        if errors:
            item["status"] = "\u4e0a\u4f20\u5931\u8d25"
            item["errors"] = [str(e) for e in errors]
            report["errors"].append({"stage": "upload", **item})
            report["files"].append(item)
            write_report(report)
            log(f"upload failed {kb_key}: {path.name}")
            return
        if not files:
            item["status"] = "\u4e0a\u4f20\u65e0\u8fd4\u56de\u6587\u6863"
            report["errors"].append({"stage": "upload_no_document", **item})
            report["files"].append(item)
            write_report(report)
            log(f"upload returned no doc {kb_key}: {path.name}")
            return

        doc, _blob = files[0]
        item["status"] = "\u5df2\u4e0a\u4f20"
        item["document_id"] = doc["id"] if isinstance(doc, dict) else doc.id
        if PARSE_AFTER_UPLOAD:
            item["parse_status"] = queue_parse(doc, report)
        else:
            item["parse_status"] = "\u4ec5\u4e0a\u4f20\uff0c\u672a\u89e6\u53d1\u89e3\u6790"
        report["files"].append(item)
        write_report(report)
        log(f"upload done {kb_key}: {path.name} -> {item['parse_status']}")
    except Exception as exc:
        item["status"] = "\u5f02\u5e38"
        item["error"] = repr(exc)
        report["errors"].append({"stage": "upload_exception", **item})
        report["files"].append(item)
        write_report(report)
        log(f"upload exception {kb_key}: {path.name}: {exc!r}")


def main() -> None:
    LOG_PATH.write_text("", encoding="utf-8")
    log("init ragflow settings")
    settings.init_settings()
    if not MANIFEST_PATH.exists():
        raise RuntimeError(f"manifest not found: {MANIFEST_PATH}")

    batch_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = load_manifest()
    report = {
        "started_at": now_text(),
        "finished_at": None,
        "tenant_id": get_target_tenant_id(),
        "manifest_path": str(MANIFEST_PATH),
        "manifest_count": len(paths),
        "batch_name": batch_name,
        "max_bytes": MAX_BYTES,
        "parse_after_upload": PARSE_AFTER_UPLOAD,
        "files": [],
        "queued": [],
        "removed_bad_documents": [],
        "errors": [],
        "final_state": [],
    }
    write_report(report)
    log(f"loaded manifest: {len(paths)} paths")

    for path in paths:
        upload_path(path, report, batch_name)

    log("collect final state")
    collect_state(report)
    report["finished_at"] = now_text()
    write_report(report)
    log(f"done, report={REPORT_PATH}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
