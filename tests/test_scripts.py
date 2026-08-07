from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


class ScriptIntegrationTests(unittest.TestCase):
    def test_scan_script_generates_inventory_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / "nas"
            out_dir = root / "out"
            cfg_dir = root / "cfg"
            cfg_dir.mkdir()

            pur = data_root / "PUR-SHR"
            sales = data_root / "SALES-SHR"
            design = data_root / "产品设计成果(2021年起)"
            for folder in (pur, sales, design):
                folder.mkdir(parents=True, exist_ok=True)

            (pur / "采购流程说明.docx").write_text("采购内容", encoding="utf-8")
            (pur / "~$临时.docx").write_text("ignore", encoding="utf-8")
            (sales / "销售方案.pdf").write_text("销售内容", encoding="utf-8")
            (sales / "临时").mkdir()
            (sales / "临时" / "skip.txt").write_text("ignore", encoding="utf-8")
            (design / "设计评审.xlsx").write_text("设计内容", encoding="utf-8")

            (cfg_dir / "knowledge_bases.yaml").write_text(
                f"""knowledge_bases:
  - id: pur_shr
    name: 采购知识库
    nas_path: /volume1/PUR-SHR
    external_mount_path: \"\"
    local_scan_path: {pur.as_posix()}
    permission_group: rag_pur_readers
    include_extensions: [.docx, .pdf, .txt, .md, .xlsx, .pptx, .csv]
  - id: sales_shr
    name: 销售知识库
    nas_path: /volume1/SALES-SHR
    external_mount_path: \"\"
    local_scan_path: {sales.as_posix()}
    permission_group: rag_sales_readers
    include_extensions: [.docx, .pdf, .txt, .md, .xlsx, .pptx, .csv]
  - id: product_design
    name: 产品设计知识库
    nas_path: /volume1/产品设计成果(2021年起)
    external_mount_path: \"\"
    local_scan_path: {design.as_posix()}
    permission_group: rag_design_readers
    include_extensions: [.docx, .pdf, .txt, .md, .xlsx, .pptx, .csv]
""",
                encoding="utf-8",
            )
            (cfg_dir / "exclude_patterns.yaml").write_text(
                """file_globs:
  - "~$*"
directory_names:
  - 临时
extension_blocklist:
  - .tmp
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/scan_nas.py",
                    "--kb-config",
                    str(cfg_dir / "knowledge_bases.yaml"),
                    "--exclude-config",
                    str(cfg_dir / "exclude_patterns.yaml"),
                    "--output-dir",
                    str(out_dir),
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertIn("扫描完成", result.stdout)

            csv_path = out_dir / "file_inventory.csv"
            sqlite_path = out_dir / "file_inventory.sqlite3"
            summary_path = out_dir / "summary.md"
            self.assertTrue(csv_path.exists())
            self.assertTrue(sqlite_path.exists())
            self.assertTrue(summary_path.exists())

            with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 5)
            candidate_rows = [row for row in rows if row["is_candidate"] == "true"]
            self.assertEqual(len(candidate_rows), 3)
            excluded_rows = [row for row in rows if row["exclude_reason"]]
            self.assertGreaterEqual(len(excluded_rows), 2)

            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("企业 NAS 三目录 RAG 文件清单汇总", summary)
            self.assertIn("采购知识库", summary)
            self.assertIn("销售知识库", summary)
            self.assertIn("产品设计知识库", summary)

    def test_sample_script_creates_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = root / "file_inventory.csv"
            samples_csv = root / "sample_plan.csv"
            samples_md = root / "sample_plan.md"

            inventory.write_text(
                """knowledge_base,knowledge_base_id,nas_path,scan_path,relative_path,filename,extension,file_size_bytes,modified_time,sha256_or_fast_hash,is_candidate,exclude_reason,parse_status,permission_group
采购知识库,pur_shr,/volume1/PUR-SHR,/mnt/nas/PUR-SHR,合同A.docx,合同A.docx,.docx,128,2026-06-25T12:00:00,fast:1,true,,pending,rag_pur_readers
采购知识库,pur_shr,/volume1/PUR-SHR,/mnt/nas/PUR-SHR,报价B.pdf,报价B.pdf,.pdf,256,2026-06-24T12:00:00,fast:2,true,,pending,rag_pur_readers
销售知识库,sales_shr,/volume1/SALES-SHR,/mnt/nas/SALES-SHR,方案C.xlsx,方案C.xlsx,.xlsx,512,2026-06-23T12:00:00,fast:3,true,,pending,rag_sales_readers
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/sample_files.py",
                    "--input",
                    str(inventory),
                    "--output-csv",
                    str(samples_csv),
                    "--output-md",
                    str(samples_md),
                    "--per-kb",
                    "1",
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertIn("抽样完成", result.stdout)
            self.assertTrue(samples_csv.exists())
            self.assertTrue(samples_md.exists())

            with samples_csv.open("r", encoding="utf-8-sig", newline="") as file:
                sampled = list(csv.DictReader(file))
            self.assertEqual(len(sampled), 2)

            md = samples_md.read_text(encoding="utf-8")
            self.assertIn("企业 NAS 三目录样本计划", md)
            self.assertIn("采购知识库", md)
            self.assertIn("销售知识库", md)


if __name__ == "__main__":
    unittest.main()
