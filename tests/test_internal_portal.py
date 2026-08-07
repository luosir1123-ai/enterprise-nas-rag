from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "internal-portal" / "backend"))

from app.document_headers import _document_response_headers  # noqa: E402


class DocumentResponseHeaderTests(unittest.TestCase):
    def test_chinese_filename_is_safe_for_http_response_headers(self) -> None:
        headers = _document_response_headers(
            {
                "content-type": "application/pdf",
                "content-disposition": 'inline; filename="K2产品规格书(1).pdf"',
                "x-content-type-options": "nosniff",
            },
            "K2产品规格书(1).pdf",
            download=False,
        )

        for value in headers.values():
            value.encode("latin-1")
        self.assertEqual(headers["content-type"], "application/pdf")
        self.assertTrue(headers["content-disposition"].startswith("inline;"))
        self.assertIn("filename*=UTF-8''K2%E4%BA%A7%E5%93%81", headers["content-disposition"])

    def test_download_uses_attachment_disposition(self) -> None:
        headers = _document_response_headers(
            {"content-type": "application/pdf"},
            "K2产品规格书(1).pdf",
            download=True,
        )

        self.assertTrue(headers["content-disposition"].startswith("attachment;"))


if __name__ == "__main__":
    unittest.main()
