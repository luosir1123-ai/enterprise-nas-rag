"""Synchronize changed NAS documents into the existing RAGFlow datasets.

Run inside the RAGFlow container. The NAS is expected at
``/ragflow/nas/LE_TOUCH_SHR`` and must be mounted read-only.

The default mode is report-only. Set ``RAGFLOW_SYNC_APPLY=1`` to upload new
documents and update modified documents in place. NAS deletions are always
reported and never deleted from RAGFlow automatically.
"""

from __future__ import annotations

import json
import os
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import xxhash

from api.db.services.doc_metadata_service import DocMetadataService
from api.db.services.document_service import DocumentService
from api.db.services.file2document_service import File2DocumentService
from api.db.services.file_service import FileService
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.task_service import TaskService
from common import settings
from common.constants import TaskStatus
from rag.nlp import search
from ragflow_env import get_target_tenant_id
from business_metadata import infer_business_metadata
from nas_sync_policy import (
    is_current_source,
    missing_document_action,
    prioritize_changes,
)


NAS_ROOT = Path("/ragflow/nas/LE_TOUCH_SHR")
REPORT_PATH = Path(os.getenv("RAGFLOW_SYNC_REPORT_PATH", "/tmp/ragflow_incremental_sync_report.json"))
LOG_PATH = Path(os.getenv("RAGFLOW_SYNC_LOG_PATH", "/tmp/ragflow_incremental_sync.log"))
APPLY = os.getenv("RAGFLOW_SYNC_APPLY", "0").lower() in {"1", "true", "yes", "y"}
PARSE = os.getenv("RAGFLOW_SYNC_PARSE", "1").lower() in {"1", "true", "yes", "y"}
MAX_CHANGES = int(os.getenv("RAGFLOW_SYNC_MAX_CHANGES", "100"))
MAX_BYTES = int(os.getenv("RAGFLOW_SYNC_MAX_BYTES", str(500 * 1024 * 1024)))
SOURCE_NAS_ID = os.getenv("RAGFLOW_SYNC_SOURCE_ID", "synology-192.0.2.90").strip()
SOURCE_NAS_NAME = os.getenv("RAGFLOW_SYNC_SOURCE_NAME", "LeTouch NAS 2026").strip()

ALLOWED_SUFFIXES = {".docx", ".xlsx", ".xlsm", ".pptx", ".pdf", ".txt", ".md", ".csv"}
EXCLUDED_DIRS = {"#recycle", "@eadir", "__macosx", "临时", "草稿"}
EXCLUDED_PREFIXES = ("~$", ".~")

KB_RULES = {
    "purchase": {
        "name": "\u91c7\u8d2d\u77e5\u8bc6\u5e93",
        "root": NAS_ROOT / "PUR-SHR",
        "permission_group": "purchase",
    },
    "sales": {
        "name": "\u9500\u552e\u77e5\u8bc6\u5e93",
        "root": NAS_ROOT / "SALES-SHR",
        "permission_group": "sales",
    },
    "product_design": {
        "name": "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u8bc6\u5e93",
        "root": NAS_ROOT / "\u4ea7\u54c1\u8bbe\u8ba1\u6210\u679c(2021\u5e74\u8d77)",
        "permission_group": "product_design",
    },
}


class NasUploadFile:
    def __init__(self, path: Path, doc_id: str | None = None):
        self.path = path
        self.filename = path.name
        if doc_id:
            self.id = doc_id

    def read(self) -> bytes:
        return self.path.read_bytes()


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    line = f"[{now_text()}] {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def write_report(report: dict) -> None:
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_path(value: str) -> str:
    value = unicodedata.normalize("NFC", str(value or "")).replace("\\", "/")
    return value.strip("/")


def safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def content_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = xxhash.xxh128()
    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def iter_candidates(root: Path):
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name for name in dirnames if name.lower() not in EXCLUDED_DIRS and not name.startswith(".")
        )
        for filename in sorted(filenames):
            if filename.startswith(EXCLUDED_PREFIXES) or filename.startswith("."):
                continue
            path = Path(current_root) / filename
            if path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size <= 0:
                continue
            yield path, stat


def get_kb(name: str):
    ok, kb = KnowledgebaseService.get_by_name(name, get_target_tenant_id())
    if not ok:
        raise RuntimeError(f"dataset not found: {name}")
    return kb


def storage_exists(doc) -> bool:
    try:
        bucket, name = File2DocumentService.get_storage_address(doc_id=doc.id)
        return bool(settings.STORAGE_IMPL.obj_exist(bucket, name))
    except Exception:
        return False


def build_metadata(existing: dict, kb_key: str, kb_name: str, root: Path, path: Path, stat, batch: str) -> dict:
    relative = normalize_path(path.relative_to(root))
    parent = normalize_path(Path(relative).parent)
    if parent == ".":
        parent = ""
    meta = dict(existing or {})
    previous_version = str(meta.get("source_version") or "")
    source_version = f"{int(stat.st_mtime)}-{int(stat.st_size)}"
    meta.update(
        {
            "knowledge_base": kb_key,
            "knowledge_base_name": kb_name,
            "permission_group": KB_RULES[kb_key]["permission_group"],
            "permission_groups": [KB_RULES[kb_key]["permission_group"]],
            "source_system": "nas_nfs",
            "source_nas_id": SOURCE_NAS_ID,
            "source_nas_name": SOURCE_NAS_NAME,
            "source_generation": "current",
            "document_lifecycle": "current",
            "effective_status": "active",
            "source_version": source_version,
            "nas_abs_path": str(path),
            "nas_root_name": root.name,
            "nas_relative_path": relative,
            "nas_parent_path": parent,
            "nas_top_folder": relative.split("/", 1)[0] if relative else "",
            "nas_mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "nas_mtime_epoch": int(stat.st_mtime),
            "file_ext": path.suffix.lower(),
            "file_size_bytes": int(stat.st_size),
            "file_size_mb": round(stat.st_size / 1024 / 1024, 3),
            "sync_status": "active",
            "sync_batch": batch,
            "last_seen_at": now_text(),
            "last_synced_at": now_text(),
        }
    )
    meta.update(infer_business_metadata(relative, kb_key=kb_key))
    if previous_version and previous_version != source_version:
        meta["previous_source_version"] = previous_version
    meta.setdefault("source_first_seen_at", now_text())
    meta.pop("source_missing_since", None)
    return meta


def build_missing_metadata(existing: dict, batch: str) -> dict:
    meta = dict(existing or {})
    meta.update(
        {
            "document_lifecycle": "retained",
            "effective_status": "historical",
            "sync_status": "missing_from_source",
            "source_missing_since": meta.get("source_missing_since") or now_text(),
            "sync_batch": batch,
            "last_synced_at": now_text(),
        }
    )
    return meta


def build_legacy_metadata(existing: dict, batch: str) -> dict:
    meta = dict(existing or {})
    meta.update(
        {
            "source_system": meta.get("source_system") or "nas_legacy_snapshot",
            "source_nas_id": meta.get("source_nas_id") or "legacy-nas-before-2026",
            "source_nas_name": meta.get("source_nas_name") or "LeTouch historical NAS",
            "source_generation": "legacy",
            "document_lifecycle": "retained",
            "effective_status": "historical",
            "sync_status": "historical",
            "sync_batch": batch,
            "last_synced_at": now_text(),
        }
    )
    return meta


def queue_reparse(doc, tenant_id: str) -> None:
    old_chunks = int(doc.chunk_num or 0)
    old_tokens = int(doc.token_num or 0)
    if old_chunks or old_tokens:
        DocumentService.clear_chunk_num_when_rerun(doc.id)
    DocumentService.update_by_id(
        doc.id,
        {
            "run": str(TaskStatus.RUNNING.value),
            "progress": 0,
            "progress_msg": "",
            "chunk_num": 0,
            "token_num": 0,
        },
    )
    TaskService.filter_delete([TaskService.model.doc_id == doc.id])
    index_name = search.index_name(tenant_id)
    if settings.docStoreConn.index_exist(index_name, doc.kb_id):
        settings.docStoreConn.delete({"doc_id": doc.id}, index_name, doc.kb_id)
    ok, fresh = DocumentService.get_by_id(doc.id)
    if not ok:
        raise RuntimeError(f"updated document missing: {doc.id}")
    DocumentService.run(tenant_id, fresh.to_dict(), {})


def classify_kb(kb_key: str, rule: dict, report: dict) -> tuple[object, list[dict], dict[str, dict]]:
    kb = get_kb(rule["name"])
    docs = list(DocumentService.query(kb_id=kb.id))
    docs_by_id = {doc.id: doc for doc in docs}
    metadata = DocMetadataService.get_metadata_for_documents(None, kb.id)

    by_path: dict[str, list[str]] = defaultdict(list)
    by_name_size: dict[tuple[str, int], list[str]] = defaultdict(list)
    for doc in docs:
        meta = metadata.get(doc.id, {})
        relative = normalize_path(meta.get("nas_relative_path", ""))
        if relative:
            by_path[relative].append(doc.id)
        by_name_size[(unicodedata.normalize("NFC", doc.name), int(doc.size or 0))].append(doc.id)

    candidate_entries = list(iter_candidates(rule["root"]))
    reserved_exact_doc_ids = set()
    for candidate_path, _candidate_stat in candidate_entries:
        candidate_relative = normalize_path(candidate_path.relative_to(rule["root"]))
        reserved_exact_doc_ids.update(by_path.get(candidate_relative, []))

    current_paths = set()
    matched_doc_ids = set()
    changes = []
    counters = defaultdict(int)
    for path, stat in candidate_entries:
        relative = normalize_path(path.relative_to(rule["root"]))
        current_paths.add(relative)
        item = {
            "kb_key": kb_key,
            "knowledge_base": kb.name,
            "path": str(path),
            "relative_path": relative,
            "filename": path.name,
            "size": int(stat.st_size),
            "mtime_epoch": int(stat.st_mtime),
        }
        candidate_ids = by_path.get(relative, [])
        if candidate_ids:
            doc_id = next(
                (candidate_id for candidate_id in candidate_ids if is_current_source(metadata.get(candidate_id, {}), SOURCE_NAS_ID)),
                candidate_ids[0],
            )
            doc = docs_by_id[doc_id]
            meta = metadata.get(doc_id, {})
            item["document_id"] = doc_id
            matched_doc_ids.add(doc_id)
            old_size = safe_int(meta.get("file_size_bytes"), int(doc.size or 0))
            old_mtime = safe_int(meta.get("nas_mtime_epoch"))
            metadata_is_current = is_current_source(meta, SOURCE_NAS_ID) and meta.get("sync_status") == "active"
            if old_size == stat.st_size and old_mtime == int(stat.st_mtime):
                item["action"] = "unchanged" if metadata_is_current else "metadata_refresh"
            elif old_size == stat.st_size and doc.content_hash and content_hash(path) == doc.content_hash:
                item["action"] = "metadata_refresh"
            else:
                item["action"] = "modified"
            counters[item["action"]] += 1
            if item["action"] != "unchanged":
                changes.append(item)
            continue

        legacy_ids = by_name_size.get((unicodedata.normalize("NFC", path.name), int(stat.st_size)), [])
        unmatched_legacy_ids = [
            doc_id
            for doc_id in legacy_ids
            if doc_id not in matched_doc_ids and doc_id not in reserved_exact_doc_ids
        ]
        if len(unmatched_legacy_ids) == 1:
            item["action"] = "metadata_refresh"
            item["document_id"] = unmatched_legacy_ids[0]
            matched_doc_ids.add(unmatched_legacy_ids[0])
        elif legacy_ids:
            item["action"] = "duplicate_current_path"
            item["document_id"] = legacy_ids[0]
            item["duplicate_document_ids"] = legacy_ids[:10]
        else:
            item["action"] = "added"
        counters[item["action"]] += 1
        if item["action"] != "duplicate_current_path":
            changes.append(item)

    missing_current = []
    legacy_retained = []
    for doc in docs:
        if doc.id in matched_doc_ids:
            continue
        meta = metadata.get(doc.id, {})
        relative = normalize_path(meta.get("nas_relative_path", ""))
        action = missing_document_action(meta, SOURCE_NAS_ID)
        item = {
            "kb_key": kb_key,
            "relative_path": relative,
            "document_id": doc.id,
            "name": doc.name,
            "action": action or ("missing_from_current_source" if is_current_source(meta, SOURCE_NAS_ID) else "legacy_retained"),
        }
        if is_current_source(meta, SOURCE_NAS_ID):
            missing_current.append(item)
            counters["missing_from_current_source"] += 1
        else:
            legacy_retained.append(item)
            counters["legacy_retained"] += 1
        if action:
            changes.append(item)
    report["datasets"].append(
        {
            "kb_key": kb_key,
            "id": kb.id,
            "name": kb.name,
            "current_candidates": len(current_paths),
            "ragflow_documents": len(docs),
            "counts": dict(counters),
            "missing_current_sample": missing_current[:100],
            "legacy_retained_sample": legacy_retained[:100],
        }
    )
    return kb, changes, metadata


def apply_change(kb, item: dict, metadata: dict[str, dict], report: dict, batch: str) -> None:
    if report["applied_count"] >= MAX_CHANGES:
        item["result"] = "deferred_change_limit"
        report["deferred"].append(item)
        return

    action = item["action"]
    doc_id = item.get("document_id")
    if action in {"mark_missing", "mark_legacy"}:
        old_meta = metadata.get(doc_id, {})
        new_meta = (
            build_missing_metadata(old_meta, batch)
            if action == "mark_missing"
            else build_legacy_metadata(old_meta, batch)
        )
        if not DocMetadataService.update_document_metadata(doc_id, new_meta):
            raise RuntimeError(f"metadata update failed: {doc_id}")
        item["result"] = "applied"
        report["applied_count"] += 1
        report["applied"].append(item)
        return

    path = Path(item["path"])
    stat = path.stat()
    if MAX_BYTES > 0 and stat.st_size > MAX_BYTES:
        item["result"] = "deferred_large_file"
        report["deferred"].append(item)
        return

    tenant_id = get_target_tenant_id()
    if action == "metadata_refresh":
        ok, doc = DocumentService.get_by_id(doc_id)
        if not ok:
            raise RuntimeError(f"document missing: {doc_id}")
    elif action == "modified":
        ok, old_doc = DocumentService.get_by_id(doc_id)
        if not ok or not storage_exists(old_doc):
            raise RuntimeError(f"document unavailable for update: {doc_id}")
        errors, files = FileService.upload_document(kb, [NasUploadFile(path, doc_id)], tenant_id, src="local")
        if errors:
            raise RuntimeError("; ".join(str(error) for error in errors))
        ok, doc = DocumentService.get_by_id(doc_id)
        if not ok:
            raise RuntimeError(f"updated document missing: {doc_id}")
        if files and PARSE:
            queue_reparse(doc, tenant_id)
            item["parse_status"] = "queued_reparse"
        elif files:
            item["parse_status"] = "uploaded_not_parsed"
        else:
            item["parse_status"] = "content_unchanged"
    elif action == "added":
        parent_path = f"nas-incremental/{batch}/{item['kb_key']}"
        errors, files = FileService.upload_document(kb, [NasUploadFile(path)], tenant_id, src="local", parent_path=parent_path)
        if errors or not files:
            raise RuntimeError("; ".join(str(error) for error in errors) or "upload returned no document")
        created, _blob = files[0]
        created_id = created["id"] if isinstance(created, dict) else created.id
        item["document_id"] = created_id
        ok, doc = DocumentService.get_by_id(created_id)
        if not ok:
            raise RuntimeError(f"created document missing: {created_id}")
        if PARSE:
            DocumentService.update_by_id(doc.id, {"run": str(TaskStatus.RUNNING.value), "progress": 0})
            ok, fresh = DocumentService.get_by_id(doc.id)
            if not ok:
                raise RuntimeError(f"created document missing before parse: {doc.id}")
            DocumentService.run(tenant_id, fresh.to_dict(), {})
            item["parse_status"] = "queued_parse"
        else:
            item["parse_status"] = "uploaded_not_parsed"
    else:
        return

    old_meta = metadata.get(item["document_id"], {})
    new_meta = build_metadata(old_meta, item["kb_key"], kb.name, KB_RULES[item["kb_key"]]["root"], path, stat, batch)
    if not DocMetadataService.update_document_metadata(item["document_id"], new_meta):
        raise RuntimeError(f"metadata update failed: {item['document_id']}")
    item["result"] = "applied"
    report["applied_count"] += 1
    report["applied"].append(item)


def main() -> None:
    LOG_PATH.write_text("", encoding="utf-8")
    settings.init_settings()
    batch = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "started_at": now_text(),
        "finished_at": None,
        "batch": batch,
        "apply": APPLY,
        "parse": PARSE,
        "max_changes": MAX_CHANGES,
        "max_bytes": MAX_BYTES,
        "source_nas_id": SOURCE_NAS_ID,
        "source_nas_name": SOURCE_NAS_NAME,
        "deletion_policy": "retain_and_mark_historical",
        "datasets": [],
        "changes": [],
        "applied": [],
        "deferred": [],
        "errors": [],
        "applied_count": 0,
    }
    write_report(report)

    if not NAS_ROOT.is_mount():
        raise RuntimeError(f"NAS root is not a mount point: {NAS_ROOT}")

    contexts = []
    for kb_key, rule in KB_RULES.items():
        if not rule["root"].is_dir():
            report["errors"].append({"kb_key": kb_key, "error": f"missing root: {rule['root']}"})
            continue
        log(f"scan {kb_key}: {rule['root']}")
        kb, changes, metadata = classify_kb(kb_key, rule, report)
        contexts.append((kb, changes, metadata))
        report["changes"].extend(changes)
        write_report(report)

    if APPLY:
        context_by_kb = {changes[0]["kb_key"]: (kb, metadata) for kb, changes, metadata in contexts if changes}
        for item in prioritize_changes(report["changes"]):
            if report["applied_count"] >= MAX_CHANGES:
                item["result"] = "deferred_change_limit"
                report["deferred"].append(item)
                continue
            kb, metadata = context_by_kb[item["kb_key"]]
            try:
                apply_change(kb, item, metadata, report, batch)
            except Exception as exc:
                item["result"] = "error"
                item["error"] = repr(exc)
                report["errors"].append(item)
            if report["applied_count"] % 10 == 0 or item.get("result") == "error":
                write_report(report)
        write_report(report)

    report["finished_at"] = now_text()
    write_report(report)
    log(f"done: apply={APPLY} changes={len(report['changes'])} applied={report['applied_count']}")
    print(json.dumps({key: value for key, value in report.items() if key not in {"changes", "applied", "deferred"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
