"""Controlled NAS-to-RAGFlow batch importer.

Run inside the RAGFlow container with `/ragflow` as working directory.

This script is intentionally ASCII-only. Chinese dataset names and NAS paths
are represented with Python Unicode escape sequences so PowerShell, SSH, and
Docker copies do not corrupt path text before Python executes it.
"""

from __future__ import annotations

import json
import os
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Iterable

from api.db.services.document_service import DocumentService
from api.db.services.file2document_service import File2DocumentService
from api.db.services.file_service import FileService
from api.db.services.knowledgebase_service import KnowledgebaseService
from common import settings
from common.constants import TaskStatus


TENANT_ID = "<configure-RAGFLOW_TENANT_ID>"
NAS_ROOT = Path("/ragflow/nas/LE_TOUCH_SHR")
REPORT_PATH = Path("/tmp/ragflow_controlled_batch_import_report.json")
LOG_PATH = Path("/tmp/ragflow_controlled_batch_import.log")

ALLOWED_SUFFIXES = {".docx", ".xlsx", ".xlsm", ".pptx", ".pdf", ".txt", ".md", ".csv"}
EXCLUDED_SUFFIXES = {".tmp", ".bak", ".exe", ".dll", ".zip", ".rar", ".7z"}
EXCLUDED_DIR_KEYWORDS = {
    "__MACOSX",
    "\u56de\u6536\u7ad9",
    "\u4e34\u65f6",
    "\u8349\u7a3f",
    "@eaDir",
}
EXCLUDED_NAME_PREFIXES = ("~$", ".~")

MAX_FILES_PER_KB = 25
MAX_BYTES = 8 * 1024 * 1024
MAX_SCAN_DIRS_PER_KB = 180
MAX_SCAN_FILES_PER_KB = 1600
MAX_SCAN_DEPTH = 5

KBS = {
    "purchase": {
        "name": "\u91c7\u8d2d\u77e5\u8bc6\u5e93",
        "root": NAS_ROOT / "PUR-SHR",
        "priority_dirs": [
            "2026/\u6570\u636e\u7ebf-\u8fde\u5c55",
            "2026/\u65e0\u7ebf\u5145-\u84dd\u949b\u601d",
            "2026/tag-\u5408\u626c",
            "2025/\u5145\u7535\u5668+\u79fb\u52a8\u7535\u6e90-\u8baf\u5929\u5b8f",
        ],
    },
    "sales": {
        "name": "\u9500\u552e\u77e5\u8bc6\u5e93",
        "root": NAS_ROOT / "SALES-SHR",
        "priority_dirs": [
            "Certificates",
            "QA+\u9a8c\u5382",
            ".",
        ],
    },
    "product_design": {
        "name": "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u8bc6\u5e93",
        "root": NAS_ROOT / "\u4ea7\u54c1\u8bbe\u8ba1\u6210\u679c(2021\u5e74\u8d77)",
        "priority_dirs": [
            "LT-C23 Find My\u6570\u636e\u7ebf",
            "LT-G20 20W \u997c\u5e72 \u6c34\u8f6c\u5370 \u5355C\u5145\u7535\u5668",
            ".",
        ],
    },
}


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


def is_excluded(path: Path) -> tuple[bool, str]:
    name = path.name
    suffix = path.suffix.lower()
    if name.startswith(EXCLUDED_NAME_PREFIXES):
        return True, "\u4e34\u65f6\u6587\u4ef6"
    if suffix in EXCLUDED_SUFFIXES:
        return True, f"\u6392\u9664\u540e\u7f00 {suffix}"
    if suffix not in ALLOWED_SUFFIXES:
        return True, f"\u6682\u4e0d\u652f\u6301\u540e\u7f00 {suffix or 'none'}"
    if set(path.parts).intersection(EXCLUDED_DIR_KEYWORDS):
        return True, "\u6392\u9664\u76ee\u5f55"
    return False, ""


def safe_parent_path(kb_key: str, batch_name: str) -> str:
    # Keep MinIO locations ASCII-only; the real NAS path remains in the report.
    return f"nas-controlled/{batch_name}/{kb_key}"


def get_kb(name: str):
    ok, kb = KnowledgebaseService.get_by_name(name, TENANT_ID)
    if not ok:
        raise RuntimeError(f"dataset not found: {name}")
    return kb


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
        DocumentService.remove_document(doc, TENANT_ID)
        report["removed_bad_documents"].append(
            {
                "document_id": doc.id,
                "name": doc.name,
                "reason": "\u5bf9\u8c61\u5b58\u50a8\u6587\u4ef6\u4e0d\u5b58\u5728\uff0c\u6e05\u7406 RAGFlow \u574f\u8bb0\u5f55\u540e\u91cd\u4f20",
            }
        )
    except Exception as exc:
        report["errors"].append(
            {
                "stage": "remove_bad_doc",
                "document_id": doc.id,
                "name": doc.name,
                "error": repr(exc),
            }
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
        DocumentService.run(TENANT_ID, fresh.to_dict(), {})
        report["queued"].append({"document_id": fresh.id, "name": fresh.name})
        return "\u5df2\u89e6\u53d1\u89e3\u6790"
    except Exception as exc:
        report["errors"].append(
            {
                "stage": "queue_parse",
                "document_id": fresh.id,
                "name": fresh.name,
                "error": repr(exc),
            }
        )
        return f"queue_parse_failed: {exc!r}"


def bounded_walk_files(base: Path, root: Path, report: dict, kb_key: str) -> Iterable[Path]:
    queue: list[tuple[Path, int]] = [(base, 0)]
    scanned_dirs = 0
    scanned_files = 0

    while queue:
        current, depth = queue.pop(0)
        if scanned_dirs >= MAX_SCAN_DIRS_PER_KB:
            report["scan_limits"].append(
                {
                    "kb_key": kb_key,
                    "base": str(base.relative_to(root) if base != root else "."),
                    "reason": "\u8fbe\u5230\u76ee\u5f55\u626b\u63cf\u4e0a\u9650",
                    "max_scan_dirs": MAX_SCAN_DIRS_PER_KB,
                }
            )
            return
        scanned_dirs += 1

        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            report["errors"].append(
                {"stage": "scan_dir", "kb_key": kb_key, "path": str(current), "error": repr(exc)}
            )
            continue

        entries.sort(key=lambda e: (not e.is_file(follow_symlinks=False), e.name.lower()))
        for entry in entries:
            path = Path(entry.path)
            try:
                if entry.is_file(follow_symlinks=False):
                    scanned_files += 1
                    if scanned_files > MAX_SCAN_FILES_PER_KB:
                        report["scan_limits"].append(
                            {
                                "kb_key": kb_key,
                                "base": str(base.relative_to(root) if base != root else "."),
                                "reason": "\u8fbe\u5230\u6587\u4ef6\u626b\u63cf\u4e0a\u9650",
                                "max_scan_files": MAX_SCAN_FILES_PER_KB,
                            }
                        )
                        return
                    yield path
                elif entry.is_dir(follow_symlinks=False) and depth < MAX_SCAN_DEPTH:
                    if entry.name not in EXCLUDED_DIR_KEYWORDS:
                        queue.append((path, depth + 1))
            except OSError as exc:
                report["errors"].append(
                    {"stage": "scan_entry", "kb_key": kb_key, "path": str(path), "error": repr(exc)}
                )


def iter_candidates(root: Path, priority_dirs: Iterable[str], report: dict, kb_key: str) -> Iterable[Path]:
    seen: set[Path] = set()
    for rel_dir in priority_dirs:
        base = root if rel_dir == "." else root / rel_dir
        if not base.exists():
            report["missing_priority_dirs"].append({"kb_key": kb_key, "relative_dir": rel_dir, "path": str(base)})
            continue

        log(f"scan {kb_key}: {base}")
        for path in bounded_walk_files(base, root, report, kb_key):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            excluded, _reason = is_excluded(path)
            if not excluded:
                yield path


def collect_files(kb_key: str, kb_def: dict, already_docs: set[str], report: dict) -> list[Path]:
    selected: list[Path] = []
    skipped = []
    root = kb_def["root"]
    if not root.exists():
        report["errors"].append({"stage": "collect", "kb": kb_key, "error": f"NAS path not found: {root}"})
        return selected

    for path in iter_candidates(root, kb_def["priority_dirs"], report, kb_key):
        rel = str(path.relative_to(root))
        try:
            size = path.stat().st_size
        except OSError as exc:
            skipped.append({"relative_path": rel, "reason": f"stat failed: {exc!r}"})
            continue
        if size <= 0:
            skipped.append({"relative_path": rel, "reason": "\u7a7a\u6587\u4ef6"})
            continue
        if size > MAX_BYTES:
            skipped.append({"relative_path": rel, "reason": f"larger than {MAX_BYTES} bytes"})
            continue
        if norm_name(path.name) in already_docs:
            skipped.append({"relative_path": rel, "reason": "\u540c\u540d\u6587\u6863\u5df2\u5b58\u5728"})
            continue

        selected.append(path)
        log(f"selected {kb_key}: {rel}")
        if len(selected) >= MAX_FILES_PER_KB:
            break

    report["selection"][kb_key] = {
        "root": str(root),
        "selected_count": len(selected),
        "selected": [str(p.relative_to(root)) for p in selected],
        "skipped_sample": skipped[:50],
    }
    return selected


def upload_one(kb_key: str, kb, path: Path, report: dict, batch_name: str) -> None:
    item = {
        "knowledge_base": kb.name,
        "kb_key": kb_key,
        "nas_path": str(path),
        "filename": path.name,
        "size": path.stat().st_size,
    }
    started = time.time()
    log(f"upload start {kb_key}: {path.name}")

    existing = doc_by_name(kb.id, path.name)
    if existing:
        if not storage_exists(existing):
            remove_bad_doc(existing, report)
        else:
            item["status"] = "\u5df2\u5b58\u5728"
            item["document_id"] = existing.id
            item["parse_status"] = queue_parse(existing, report)
            report["files"].append(item)
            write_report(report)
            log(f"already exists {kb_key}: {path.name} -> {item['parse_status']}")
            return

    try:
        errors, files = FileService.upload_document(
            kb,
            [LocalUploadFile(path)],
            TENANT_ID,
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
            log(f"upload returned no document {kb_key}: {path.name}")
            return

        doc, _blob = files[0]
        doc_id = doc["id"] if isinstance(doc, dict) else doc.id
        item["status"] = "\u5df2\u4e0a\u4f20"
        item["document_id"] = doc_id
        item["parse_status"] = queue_parse(doc, report)
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


def collect_state(report: dict) -> None:
    datasets = []
    for kb_key, kb_def in KBS.items():
        kb = get_kb(kb_def["name"])
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


def main() -> None:
    LOG_PATH.write_text("", encoding="utf-8")
    log("init ragflow settings")
    settings.init_settings()
    if not NAS_ROOT.exists():
        raise RuntimeError(f"NAS mount path not found: {NAS_ROOT}")

    batch_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "started_at": now_text(),
        "finished_at": None,
        "tenant_id": TENANT_ID,
        "nas_root": str(NAS_ROOT),
        "max_files_per_kb": MAX_FILES_PER_KB,
        "max_bytes": MAX_BYTES,
        "max_scan_dirs_per_kb": MAX_SCAN_DIRS_PER_KB,
        "max_scan_files_per_kb": MAX_SCAN_FILES_PER_KB,
        "max_scan_depth": MAX_SCAN_DEPTH,
        "batch_name": batch_name,
        "selection": {},
        "scan_limits": [],
        "missing_priority_dirs": [],
        "files": [],
        "queued": [],
        "removed_bad_documents": [],
        "errors": [],
        "final_state": [],
    }
    write_report(report)

    for kb_key, kb_def in KBS.items():
        log(f"start kb {kb_key}")
        kb = get_kb(kb_def["name"])
        existing_names = {
            norm_name(doc.name)
            for doc in DocumentService.query(kb_id=kb.id)
            if storage_exists(doc)
        }
        selected = collect_files(kb_key, kb_def, existing_names, report)
        write_report(report)
        log(f"selected {len(selected)} files for {kb_key}")
        for path in selected:
            upload_one(kb_key, kb, path, report, batch_name)

    log("collect final state")
    collect_state(report)
    report["finished_at"] = now_text()
    write_report(report)
    log(f"done, report={REPORT_PATH}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
