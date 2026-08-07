"""Make a small controlled upload manifest for RAGFlow.

Run inside the RAGFlow container with `/ragflow` as working directory.

This script is ASCII-only. Chinese paths use Unicode escape sequences to avoid
encoding damage while copying through PowerShell, SSH, and Docker.
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
from api.db.services.knowledgebase_service import KnowledgebaseService
from common import settings
from ragflow_env import get_target_tenant_id


NAS_ROOT = Path("/ragflow/nas/LE_TOUCH_SHR")
MANIFEST_PATH = Path("/tmp/ragflow_upload_manifest.txt")
REPORT_PATH = Path("/tmp/ragflow_upload_manifest_make_report.json")
LOG_PATH = Path("/tmp/ragflow_upload_manifest_make.log")

ALLOWED_SUFFIXES = {".docx", ".xlsx", ".xlsm", ".pptx", ".pdf", ".txt", ".md", ".csv"}
EXCLUDED_NAME_PREFIXES = ("~$", ".~")
MAX_BYTES = int(os.getenv("RAGFLOW_MANIFEST_MAX_BYTES", str(8 * 1024 * 1024)))
MAX_TOTAL_PER_KB = int(os.getenv("RAGFLOW_MANIFEST_MAX_TOTAL_PER_KB", "12"))
MAX_SCAN_SECONDS_PER_KB = int(os.getenv("RAGFLOW_MANIFEST_MAX_SCAN_SECONDS_PER_KB", "90"))
MAX_SCAN_DIRS_PER_PRIORITY = int(os.getenv("RAGFLOW_MANIFEST_MAX_SCAN_DIRS_PER_PRIORITY", "60"))
MAX_SCAN_FILES_PER_PRIORITY = int(os.getenv("RAGFLOW_MANIFEST_MAX_SCAN_FILES_PER_PRIORITY", "500"))
MAX_DEPTH = int(os.getenv("RAGFLOW_MANIFEST_MAX_DEPTH", "4"))

KB_RULES = {
    "purchase": {
        "name": "\u91c7\u8d2d\u77e5\u8bc6\u5e93",
        "root": NAS_ROOT / "PUR-SHR",
        "priority_dirs": [
            "2026/\u6570\u636e\u7ebf-\u8fde\u5c55",
            "2026/\u65e0\u7ebf\u5145-\u84dd\u949b\u601d",
            "2026/tag-\u5408\u626c",
            "2025/\u5145\u7535\u5668+\u79fb\u52a8\u7535\u6e90-\u8baf\u5929\u5b8f",
            ".",
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

EXACT_PATHS = [
    NAS_ROOT / "PUR-SHR/2026/\u6570\u636e\u7ebf-\u8fde\u5c55/\u5de5\u5382\u8d44\u6599/ISO9001\u4e2d\u6587\u8b49\u66f82027.1.26.pdf",
    NAS_ROOT / "PUR-SHR/2026/\u6570\u636e\u7ebf-\u8fde\u5c55/\u62a5\u4ef7\u5355/\u5831\u50f9\u55aeCBATB5005-100A  20260225  RMB.pdf",
    NAS_ROOT / "PUR-SHR/2026/\u6570\u636e\u7ebf-\u8fde\u5c55/\u4ea7\u54c1\u8d44\u6599/\u96f7\u75354\u62a5\u544a/Acon Type-C 1m EPR TBT4 Cable Report 2022-05-05\u8bc1\u4e66.pdf",
    NAS_ROOT / "PUR-SHR/2026/\u6570\u636e\u7ebf-\u8fde\u5c55/\u4ea7\u54c1\u8d44\u6599/\u96f7\u75355\u62a5\u544a/Thunderbolt E-Marker Cable_ACON_CBATB5005-100A_Rev 1.0.pdf",
    NAS_ROOT / "PUR-SHR/2026/\u6570\u636e\u7ebf-\u8fde\u5c55/\u4ea7\u54c1\u8d44\u6599/\u96f7\u75355\u89c4\u683c\u4e66/CBATB5005-100A01.pdf",
    NAS_ROOT / "PUR-SHR/2026/\u65e0\u7ebf\u5145-\u84dd\u949b\u601d/\u62a5\u4ef7\u5355/SW09\u65e0\u7ebf\u5145\u62a5\u4ef7\u5355260127.pdf",
    NAS_ROOT / "PUR-SHR/2026/\u65e0\u7ebf\u5145-\u84dd\u949b\u601d/\u4ea7\u54c1\u8d44\u6599/SW09\u4ea7\u54c1\u89c4\u683c\u4e66.pdf",
    NAS_ROOT / "PUR-SHR/2026/tag-\u5408\u626c/\u4ea7\u54c1\u8d44\u6599/20250310\u66f4\u65b0 FM01  FM03-ASR UI\u64cd\u4f5c(LET).xlsx",
    NAS_ROOT / "PUR-SHR/2026/tag-\u5408\u626c/\u4ea7\u54c1\u8d44\u6599/onmicro\u53cc\u7cfb\u7edf\u5361\u7247\u89c4\u683c\u4e66/LT-T43-X-MARK CARD THREE-\u4ea7\u54c1\u89c4\u683c\u4e6620260121.docx",
    NAS_ROOT / "PUR-SHR/2026/tag-\u5408\u626c/\u4ea7\u54c1\u8d44\u6599/onmicro\u53cc\u7cfb\u7edf\u5361\u7247\u89c4\u683c\u4e66/LT-T43-X-MARK CARD THREE-\u4ea7\u54c1\u89c4\u683c\u4e6620260121.pdf",
]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    line = f"[{now_text()}] {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def norm_name(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def classify(path: Path):
    for kb_key, kb in KB_RULES.items():
        try:
            path.relative_to(kb["root"])
            return kb_key
        except ValueError:
            pass
    return None


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
        try:
            return bool(settings.STORAGE_IMPL.obj_exist(doc.kb_id, doc.location))
        except Exception:
            return False


def valid_existing_names(kb_key: str) -> set[str]:
    kb = get_kb(KB_RULES[kb_key]["name"])
    return {
        norm_name(doc.name)
        for doc in DocumentService.query(kb_id=kb.id)
        if storage_exists(doc)
    }


def should_include(path: Path, existing: set[str], report: dict, source: str) -> bool:
    item = {"path": str(path), "source": source}
    if not path.exists() or not path.is_file():
        item["reason"] = "missing"
        report["skipped"].append(item)
        return False
    if path.name.startswith(EXCLUDED_NAME_PREFIXES):
        item["reason"] = "temporary_file"
        report["skipped"].append(item)
        return False
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        item["reason"] = "unsupported_suffix"
        report["skipped"].append(item)
        return False
    try:
        size = path.stat().st_size
    except OSError as exc:
        item["reason"] = f"stat_failed: {exc!r}"
        report["skipped"].append(item)
        return False
    if size <= 0:
        item["reason"] = "empty"
        report["skipped"].append(item)
        return False
    if MAX_BYTES > 0 and size > MAX_BYTES:
        item["reason"] = f"too_large: {size}"
        report["skipped"].append(item)
        return False
    if norm_name(path.name) in existing:
        item["reason"] = "already_valid_uploaded"
        report["skipped"].append(item)
        return False
    return True


def bounded_walk(base: Path, report: dict, kb_key: str):
    queue: list[tuple[Path, int]] = [(base, 0)]
    dirs = 0
    files = 0
    while queue:
        current, depth = queue.pop(0)
        if dirs >= MAX_SCAN_DIRS_PER_PRIORITY:
            report["scan_limits"].append({"kb_key": kb_key, "base": str(base), "reason": "dir_limit"})
            return
        dirs += 1
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            report["scan_errors"].append({"kb_key": kb_key, "path": str(current), "error": repr(exc)})
            continue
        entries.sort(key=lambda e: (not e.is_file(follow_symlinks=False), e.name.lower()))
        for entry in entries:
            path = Path(entry.path)
            try:
                if entry.is_file(follow_symlinks=False):
                    files += 1
                    if files > MAX_SCAN_FILES_PER_PRIORITY:
                        report["scan_limits"].append({"kb_key": kb_key, "base": str(base), "reason": "file_limit"})
                        return
                    yield path
                elif entry.is_dir(follow_symlinks=False) and depth < MAX_DEPTH:
                    if not entry.name.startswith("@"):
                        queue.append((path, depth + 1))
            except OSError as exc:
                report["scan_errors"].append({"kb_key": kb_key, "path": str(path), "error": repr(exc)})


def add_candidate(path: Path, selected: dict[str, list[Path]], existing_by_kb: dict[str, set[str]], report: dict, source: str) -> None:
    kb_key = classify(path)
    if not kb_key:
        report["skipped"].append({"path": str(path), "source": source, "reason": "not_in_three_kbs"})
        return
    if len(selected[kb_key]) >= MAX_TOTAL_PER_KB:
        return
    if should_include(path, existing_by_kb[kb_key], report, source):
        selected[kb_key].append(path)
        existing_by_kb[kb_key].add(norm_name(path.name))
        log(f"selected {kb_key}: {path}")


def main() -> None:
    LOG_PATH.write_text("", encoding="utf-8")
    log("init settings")
    settings.init_settings()

    selected: dict[str, list[Path]] = {k: [] for k in KB_RULES}
    existing_by_kb = {k: valid_existing_names(k) for k in KB_RULES}
    report = {
        "started_at": now_text(),
        "max_total_per_kb": MAX_TOTAL_PER_KB,
        "max_bytes": MAX_BYTES,
        "max_scan_seconds_per_kb": MAX_SCAN_SECONDS_PER_KB,
        "max_scan_dirs_per_priority": MAX_SCAN_DIRS_PER_PRIORITY,
        "max_scan_files_per_priority": MAX_SCAN_FILES_PER_PRIORITY,
        "max_depth": MAX_DEPTH,
        "selected": {},
        "skipped": [],
        "scan_limits": [],
        "scan_errors": [],
        "missing_priority_dirs": [],
        "finished_at": None,
    }

    for path in EXACT_PATHS:
        add_candidate(path, selected, existing_by_kb, report, "exact")

    for kb_key, kb in KB_RULES.items():
        started = time.time()
        root = kb["root"]
        if not root.exists():
            report["missing_priority_dirs"].append({"kb_key": kb_key, "path": str(root), "reason": "root_missing"})
            continue
        for rel in kb["priority_dirs"]:
            if len(selected[kb_key]) >= MAX_TOTAL_PER_KB:
                break
            if time.time() - started > MAX_SCAN_SECONDS_PER_KB:
                report["scan_limits"].append({"kb_key": kb_key, "reason": "time_limit"})
                break
            base = root if rel == "." else root / rel
            if not base.exists():
                report["missing_priority_dirs"].append({"kb_key": kb_key, "path": str(base)})
                continue
            log(f"scan {kb_key}: {base}")
            for path in bounded_walk(base, report, kb_key):
                add_candidate(path, selected, existing_by_kb, report, "scan")
                if len(selected[kb_key]) >= MAX_TOTAL_PER_KB:
                    break
                if time.time() - started > MAX_SCAN_SECONDS_PER_KB:
                    report["scan_limits"].append({"kb_key": kb_key, "reason": "time_limit"})
                    break

    manifest_paths: list[Path] = []
    seen: set[str] = set()
    for kb_key in ("purchase", "sales", "product_design"):
        report["selected"][kb_key] = [str(p) for p in selected[kb_key]]
        for p in selected[kb_key]:
            key = str(p)
            if key not in seen:
                seen.add(key)
                manifest_paths.append(p)

    MANIFEST_PATH.write_text("\n".join(str(p) for p in manifest_paths) + "\n", encoding="utf-8")
    report["manifest_path"] = str(MANIFEST_PATH)
    report["manifest_count"] = len(manifest_paths)
    report["finished_at"] = now_text()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"manifest written: {MANIFEST_PATH}, count={len(manifest_paths)}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
