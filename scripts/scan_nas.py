#!/usr/bin/env python
"""只读扫描企业 NAS 三目录，生成 RAG 试点文件清单。"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


DEFAULT_OUTPUT_DIR = Path("data/inventory")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".heic"}
OFFICE_AND_PDF = {".docx", ".xlsx", ".pptx", ".pdf"}
CSV_COLUMNS = [
    "knowledge_base",
    "knowledge_base_id",
    "nas_path",
    "scan_path",
    "relative_path",
    "filename",
    "extension",
    "file_size_bytes",
    "modified_time",
    "sha256_or_fast_hash",
    "is_candidate",
    "exclude_reason",
    "parse_status",
    "permission_group",
]


@dataclass(frozen=True)
class KnowledgeBase:
    id: str
    name: str
    nas_path: str
    external_mount_path: str
    local_scan_path: str
    permission_group: str
    include_extensions: set[str]
    relative_root: str = ""

    @property
    def scan_path(self) -> Path:
        raw_path = self.local_scan_path or self.external_mount_path or self.nas_path
        return Path(raw_path)


def configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def display_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise SystemExit("缺少 PyYAML。请先执行：python -m pip install -r requirements.txt")
    with path.open("r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}
    if not isinstance(loaded, dict):
        raise SystemExit(f"配置文件格式错误：{path}")
    return loaded


def normalize_extension(value: str) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""
    return value if value.startswith(".") else f".{value}"


def read_knowledge_bases(config_path: Path) -> list[KnowledgeBase]:
    payload = load_yaml(config_path)
    items = payload.get("knowledge_bases", [])
    if not isinstance(items, list) or not items:
        raise SystemExit(f"未在 {config_path} 中找到 knowledge_bases。")

    knowledge_bases: list[KnowledgeBase] = []
    for item in items:
        include_extensions = {normalize_extension(ext) for ext in item.get("include_extensions", [])}
        knowledge_bases.append(
            KnowledgeBase(
                id=str(item["id"]),
                name=str(item["name"]),
                nas_path=str(item["nas_path"]),
                external_mount_path=str(item.get("external_mount_path", "")),
                local_scan_path=str(item.get("local_scan_path", "")),
                permission_group=str(item["permission_group"]),
                include_extensions={ext for ext in include_extensions if ext},
                relative_root=str(item.get("relative_root", "")).strip(),
            )
        )
    return knowledge_bases


def read_exclude_rules(config_path: Path) -> dict[str, Any]:
    payload = load_yaml(config_path)
    return {
        "file_globs": [str(item) for item in payload.get("file_globs", [])],
        "directory_names": {str(item).lower() for item in payload.get("directory_names", [])},
        "extension_blocklist": {
            normalize_extension(str(item)) for item in payload.get("extension_blocklist", [])
        },
    }


def should_exclude(path: Path, root: Path, rules: dict[str, Any]) -> str:
    filename_lower = path.name.lower()
    extension = path.suffix.lower()

    for pattern in rules["file_globs"]:
        if fnmatch.fnmatch(filename_lower, pattern.lower()):
            return f"文件名匹配排除规则：{pattern}"

    if extension in rules["extension_blocklist"]:
        return f"扩展名在排除列表：{extension}"

    try:
        relative_parts = path.relative_to(root).parts[:-1]
    except ValueError:
        relative_parts = path.parts[:-1]
    lower_parts = {part.lower() for part in relative_parts}
    blocked_dirs = lower_parts.intersection(rules["directory_names"])
    if blocked_dirs:
        return "目录名在排除列表：" + ",".join(sorted(blocked_dirs))

    return ""


def fast_hash(path: Path, stat_result: os.stat_result) -> str:
    payload = f"{path}|{stat_result.st_size}|{stat_result.st_mtime_ns}".encode("utf-8", errors="ignore")
    return "fast:" + hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def parse_status(extension: str, is_candidate: bool, exclude_reason: str) -> str:
    if exclude_reason:
        return "excluded"
    if not is_candidate:
        return "unsupported_extension"
    if extension in IMAGE_EXTENSIONS:
        return "needs_ocr"
    return "pending"


def iter_files(root: Path, max_depth: int | None = None):
    for current_root, dirnames, filenames in os.walk(root):
        dirnames.sort()
        filenames.sort()
        current = Path(current_root)
        if max_depth is not None:
            try:
                depth = len(current.relative_to(root).parts)
            except ValueError:
                depth = 0
            if depth >= max_depth:
                dirnames[:] = []
        for filename in filenames:
            yield current / filename


def safe_relative(path: Path, root: Path) -> str:
    try:
        return display_path(path.relative_to(root))
    except ValueError:
        return display_path(path)


def scan_knowledge_base(
    kb: KnowledgeBase,
    rules: dict[str, Any],
    use_sha256: bool,
    max_files: int | None,
    max_depth: int | None,
) -> list[dict[str, Any]]:
    root = kb.scan_path
    scan_root = root / kb.relative_root if kb.relative_root else root
    rows: list[dict[str, Any]] = []
    if not scan_root.exists():
        rows.append(
            {
                "knowledge_base": kb.name,
                "knowledge_base_id": kb.id,
                "nas_path": kb.nas_path,
                "scan_path": display_path(scan_root),
                "relative_path": "",
                "filename": "",
                "extension": "",
                "file_size_bytes": 0,
                "modified_time": "",
                "sha256_or_fast_hash": "",
                "is_candidate": "false",
                "exclude_reason": f"扫描路径不存在：{display_path(root)}",
                "parse_status": "missing_scan_path",
                "permission_group": kb.permission_group,
            }
        )
        return rows

    scanned = 0
    for file_path in iter_files(scan_root, max_depth=max_depth):
        if max_files is not None and scanned >= max_files:
            break
        scanned += 1
        try:
            stat_result = file_path.stat()
        except OSError as exc:
            rows.append(
                {
                    "knowledge_base": kb.name,
                    "knowledge_base_id": kb.id,
                    "nas_path": kb.nas_path,
                    "scan_path": display_path(scan_root),
                    "relative_path": safe_relative(file_path, scan_root),
                    "filename": file_path.name,
                    "extension": file_path.suffix.lower(),
                    "file_size_bytes": 0,
                    "modified_time": "",
                    "sha256_or_fast_hash": "",
                    "is_candidate": "false",
                    "exclude_reason": f"读取文件状态失败：{exc}",
                    "parse_status": "stat_error",
                    "permission_group": kb.permission_group,
                }
            )
            continue

        extension = file_path.suffix.lower()
        exclude_reason = should_exclude(file_path, root, rules)
        is_candidate = not exclude_reason and extension in kb.include_extensions
        try:
            file_hash = sha256_file(file_path) if use_sha256 else fast_hash(file_path, stat_result)
        except OSError as exc:
            file_hash = f"hash_error:{exc}"

        rows.append(
            {
                "knowledge_base": kb.name,
                "knowledge_base_id": kb.id,
                "nas_path": kb.nas_path,
                "scan_path": display_path(scan_root),
                "relative_path": safe_relative(file_path, scan_root),
                "filename": file_path.name,
                "extension": extension,
                "file_size_bytes": stat_result.st_size,
                "modified_time": datetime.fromtimestamp(stat_result.st_mtime).isoformat(timespec="seconds"),
                "sha256_or_fast_hash": file_hash,
                "is_candidate": str(is_candidate).lower(),
                "exclude_reason": exclude_reason,
                "parse_status": parse_status(extension, is_candidate, exclude_reason),
                "permission_group": kb.permission_group,
            }
        )
    return rows


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})


def write_sqlite(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(output_path) as connection:
        connection.execute("DROP TABLE IF EXISTS file_inventory")
        connection.execute(
            """
            CREATE TABLE file_inventory (
                knowledge_base TEXT NOT NULL,
                knowledge_base_id TEXT NOT NULL,
                nas_path TEXT NOT NULL,
                scan_path TEXT NOT NULL,
                relative_path TEXT,
                filename TEXT,
                extension TEXT,
                file_size_bytes INTEGER,
                modified_time TEXT,
                sha256_or_fast_hash TEXT,
                is_candidate TEXT,
                exclude_reason TEXT,
                parse_status TEXT,
                permission_group TEXT
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO file_inventory (
                knowledge_base, knowledge_base_id, nas_path, scan_path, relative_path,
                filename, extension, file_size_bytes, modified_time, sha256_or_fast_hash,
                is_candidate, exclude_reason, parse_status, permission_group
            ) VALUES (
                :knowledge_base, :knowledge_base_id, :nas_path, :scan_path, :relative_path,
                :filename, :extension, :file_size_bytes, :modified_time, :sha256_or_fast_hash,
                :is_candidate, :exclude_reason, :parse_status, :permission_group
            )
            """,
            rows,
        )
        connection.execute("CREATE INDEX idx_inventory_kb ON file_inventory (knowledge_base_id)")
        connection.execute("CREATE INDEX idx_inventory_ext ON file_inventory (extension)")
        connection.execute("CREATE INDEX idx_inventory_candidate ON file_inventory (is_candidate)")


def format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{value} B"


def count_recent_files(rows: list[dict[str, Any]], cutoff: datetime) -> int:
    count = 0
    for row in rows:
        raw_value = str(row.get("modified_time") or "")
        if not raw_value:
            continue
        try:
            modified = datetime.fromisoformat(raw_value)
        except ValueError:
            continue
        if modified.replace(tzinfo=None) >= cutoff.replace(tzinfo=None):
            count += 1
    return count


def write_summary(rows: list[dict[str, Any]], output_path: Path, generated_at: datetime) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    by_kb: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_kb[str(row.get("knowledge_base", "未知知识库"))].append(row)

    one_year_ago = generated_at - timedelta(days=365)
    lines: list[str] = [
        "# 企业 NAS 三目录 RAG 文件清单汇总",
        "",
        f"- 生成时间：{generated_at.isoformat(timespec='seconds')}",
        f"- 总文件记录数：{len(rows)}",
        f"- 总候选文件数：{sum(1 for row in rows if row.get('is_candidate') == 'true')}",
        "",
        "## 知识库统计",
        "",
    ]

    for kb_name, kb_rows in by_kb.items():
        total_size = sum(int(row.get("file_size_bytes") or 0) for row in kb_rows)
        candidates = [row for row in kb_rows if row.get("is_candidate") == "true"]
        excluded = [row for row in kb_rows if row.get("exclude_reason")]
        extension_counts = Counter(str(row.get("extension") or "(无扩展名)") for row in kb_rows)
        core_counts = Counter(str(row.get("extension") or "") for row in kb_rows if row.get("extension") in OFFICE_AND_PDF)
        image_candidates = [row for row in kb_rows if row.get("extension") in IMAGE_EXTENSIONS]
        recent_count = count_recent_files(kb_rows, one_year_ago)
        largest = sorted(kb_rows, key=lambda item: int(item.get("file_size_bytes") or 0), reverse=True)[:20]

        lines.extend(
            [
                f"### {kb_name}",
                "",
                f"- 总大小：{format_bytes(total_size)}",
                f"- 文件记录数：{len(kb_rows)}",
                f"- 候选文件数：{len(candidates)}",
                f"- 被排除文件数：{len(excluded)}",
                f"- 图片和扫描件候选数量：{len(image_candidates)}",
                f"- 最近一年修改文件数量：{recent_count}",
                "",
                "#### Office/PDF 数量",
                "",
            ]
        )
        for extension in [".pdf", ".docx", ".xlsx", ".pptx"]:
            lines.append(f"- `{extension}`：{core_counts.get(extension, 0)}")

        lines.extend(["", "#### 文件类型分布", ""])
        for extension, count in extension_counts.most_common():
            lines.append(f"- `{extension}`：{count}")

        lines.extend(["", "#### 最大文件 Top 20", ""])
        if largest:
            for index, row in enumerate(largest, start=1):
                path = row.get("relative_path") or row.get("filename") or "(未知文件)"
                lines.append(f"{index}. `{path}` - {format_bytes(int(row.get('file_size_bytes') or 0))}")
        else:
            lines.append("- 无文件记录。")
        lines.append("")

    lines.extend(
        [
            "## 下一步建议",
            "",
            "1. 先处理 NAS 存储管理器中的警告。",
            "2. 对每个知识库抽样 100-300 个候选文件。",
            "3. 由业务人员补充 `data/eval/eval_questions_template.csv`。",
            "4. 后续外部服务器按本清单做增量解析和 RAG 入库。",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读扫描企业 NAS 三目录，生成 RAG 文件清单。")
    parser.add_argument("--kb-config", default="configs/knowledge_bases.yaml", help="知识库配置路径。")
    parser.add_argument("--exclude-config", default="configs/exclude_patterns.yaml", help="排除规则配置路径。")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录。")
    parser.add_argument("--sha256", action="store_true", help="计算完整 SHA256。默认使用快速 hash，适合首次大目录扫描。")
    parser.add_argument("--max-files", type=int, default=None, help="每个知识库最多扫描文件数，用于试跑。")
    parser.add_argument("--max-depth", type=int, default=None, help="相对每个知识库根目录的最大递归深度，用于远程挂载试扫。0 表示只扫根目录文件。")
    return parser.parse_args(argv)


def resolve_project_path(project_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return project_root / path


def main(argv: list[str] | None = None) -> int:
    configure_stdout()
    args = parse_args(argv or sys.argv[1:])
    project_root = Path(__file__).resolve().parents[1]
    kb_config = resolve_project_path(project_root, args.kb_config)
    exclude_config = resolve_project_path(project_root, args.exclude_config)
    output_dir = resolve_project_path(project_root, args.output_dir)

    knowledge_bases = read_knowledge_bases(kb_config)
    rules = read_exclude_rules(exclude_config)

    all_rows: list[dict[str, Any]] = []
    for kb in knowledge_bases:
        all_rows.extend(
            scan_knowledge_base(
                kb=kb,
                rules=rules,
                use_sha256=args.sha256,
                max_files=args.max_files,
                max_depth=args.max_depth,
            )
        )

    generated_at = datetime.now(timezone.utc).astimezone()
    write_csv(all_rows, output_dir / "file_inventory.csv")
    write_sqlite(all_rows, output_dir / "file_inventory.sqlite3")
    write_summary(all_rows, output_dir / "summary.md", generated_at=generated_at)

    print(f"扫描完成：{len(all_rows)} 条文件记录")
    print(f"CSV：{display_path(output_dir / 'file_inventory.csv')}")
    print(f"SQLite：{display_path(output_dir / 'file_inventory.sqlite3')}")
    print(f"中文汇总：{display_path(output_dir / 'summary.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
