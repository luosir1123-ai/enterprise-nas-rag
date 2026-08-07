#!/usr/bin/env python
"""从已生成的文件清单中为每个知识库抽样候选文件。"""

from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path
import sys

DEFAULT_INPUT = Path("data/inventory/file_inventory.csv")
DEFAULT_OUTPUT_CSV = Path("data/samples/sample_plan.csv")
DEFAULT_OUTPUT_MD = Path("data/samples/sample_plan.md")


def configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从文件清单抽样候选文件。")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="文件清单 CSV 路径。")
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV), help="样本计划 CSV 输出路径。")
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD), help="样本计划 Markdown 输出路径。")
    parser.add_argument("--per-kb", type=int, default=100, help="每个知识库抽样数量。")
    parser.add_argument("--seed", type=int, default=42, help="随机种子。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdout()
    args = parse_args(argv or sys.argv[1:])
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"找不到清单文件：{input_path}")

    rows = list(csv.DictReader(input_path.open("r", encoding="utf-8-sig", newline="")))
    candidates_by_kb: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("is_candidate", "").lower() == "true":
            candidates_by_kb[row.get("knowledge_base", "未知知识库")].append(row)

    rng = random.Random(args.seed)
    sampled_rows: list[dict[str, str]] = []
    summary_lines = [
        "# 企业 NAS 三目录样本计划",
        "",
        f"- 输入清单：{input_path.as_posix()}",
        f"- 每个知识库目标抽样数：{args.per_kb}",
        f"- 随机种子：{args.seed}",
        "",
    ]

    for kb_name, kb_rows in sorted(candidates_by_kb.items()):
        extension_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in kb_rows:
            extension_groups[row.get("extension", "")].append(row)

        selected: list[dict[str, str]] = []
        preferred_extensions = [".docx", ".xlsx", ".pptx", ".pdf", ".txt", ".md", ".csv"]
        for extension in preferred_extensions:
            if len(selected) >= args.per_kb:
                break
            bucket = extension_groups.get(extension, [])
            if not bucket:
                continue
            rng.shuffle(bucket)
            for row in bucket:
                if row not in selected:
                    selected.append(row)
                if len(selected) >= max(1, args.per_kb // 2):
                    break

        if len(selected) < args.per_kb:
            remaining = [row for row in kb_rows if row not in selected]
            rng.shuffle(remaining)
            for row in remaining:
                selected.append(row)
                if len(selected) >= args.per_kb:
                    break

        sampled_rows.extend(selected)
        summary_lines.extend(
            [
                f"## {kb_name}",
                "",
                f"- 候选文件数：{len(kb_rows)}",
                f"- 实际抽样数：{len(selected)}",
                "",
            ]
        )
        if selected:
            for index, row in enumerate(selected[: min(len(selected), args.per_kb)], start=1):
                summary_lines.append(
                    f"{index}. `{row.get('relative_path', '')}` - `{row.get('extension', '')}` - {row.get('file_size_bytes', '0')} bytes"
                )
        else:
            summary_lines.append("- 没有候选文件，先完成 NAS 挂载或更新清单后再抽样。")
        summary_lines.append("")

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as file:
        if sampled_rows:
            writer = csv.DictWriter(file, fieldnames=list(sampled_rows[0].keys()))
            writer.writeheader()
            writer.writerows(sampled_rows)
        else:
            file.write("")

    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(summary_lines), encoding="utf-8")

    print(f"抽样完成：{len(sampled_rows)} 条样本")
    print(f"CSV：{output_csv.as_posix()}")
    print(f"Markdown：{output_md.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
