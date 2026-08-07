import sys
import sqlite3
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from ragflow_build_excel_row_index import (  # noqa: E402
    canonical_header,
    create_schema,
    detect_header,
    extract_row_models,
    index_workbook_blob,
    parse_business_value,
    parse_numeric,
)


class ExcelRowIndexHelperTest(unittest.TestCase):
    def test_detects_purchase_and_sales_headers(self):
        self.assertEqual(canonical_header("型号"), "model")
        self.assertEqual(canonical_header("Unit Price"), "unit_price")
        self.assertEqual(canonical_header("成本价"), "cost_price")
        self.assertIsNotNone(detect_header(["序号", "型号", "品名", "单价 2-1Kpcs"]))
        self.assertIsNotNone(detect_header(["Model", "Feature", "MOQ", "供应商", "成本价"]))

    def test_extracts_model_split_by_line_break(self):
        self.assertEqual(extract_row_models("GS-\n30W0989"), ["GS-30W0989"])
        self.assertEqual(extract_row_models("LT-W80"), ["LT-W80"])

    def test_parses_simple_numeric_values_and_units(self):
        self.assertEqual(parse_numeric("3000PCS"), (3000.0, "PCS"))
        self.assertEqual(parse_numeric("￥46.45"), (46.45, "¥"))
        self.assertEqual(parse_numeric("US$6-6.5"), (None, ""))

    def test_normalizes_business_ranges_currency_and_tax(self):
        value = parse_business_value("US$6-6.5", "含税报价 2KPCS", "unit_price")
        self.assertEqual(value["numeric_min"], 6.0)
        self.assertEqual(value["numeric_max"], 6.5)
        self.assertEqual(value["currency"], "USD")
        self.assertEqual(value["tax_status"], "tax_included")
        self.assertEqual(value["quantity_basis"], "含税报价 2KPCS")

    def test_indexes_multirow_headers_and_model_aliases(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "美规报价"
        sheet.append(["产品信息", "", "价格信息", ""])
        sheet.append(["序号", "Model", "MOQ", "含税报价"])
        sheet.append([1, "LT-W80", "3000PCS", "US$6-6.5"])
        stream = BytesIO()
        workbook.save(stream)

        document = {
            "document_id": "doc-structured",
            "document_name": "报价.xlsx",
            "kb_id": "kb-purchase",
            "kb_key": "purchase",
            "storage_bucket": "bucket",
            "storage_name": "object",
            "content_hash": "a" * 64,
            "source_hash": "b" * 32,
            "size_bytes": len(stream.getvalue()),
            "effective_status": "active",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.sqlite3"
            with sqlite3.connect(path) as connection:
                create_schema(connection)
                report = index_workbook_blob(connection, document, stream.getvalue())
                connection.commit()
                aliases = {
                    row[0] for row in connection.execute("SELECT model FROM row_models")
                }
                field = connection.execute(
                    "SELECT numeric_min,numeric_max,currency,tax_status FROM row_fields "
                    "WHERE field_key='unit_price'"
                ).fetchone()
            self.assertEqual(report["rows"], 1)
            self.assertIn("LT-W80", aliases)
            self.assertIn("LTW80", aliases)
            self.assertEqual(field, (6.0, 6.5, "USD", "tax_included"))


if __name__ == "__main__":
    unittest.main()
