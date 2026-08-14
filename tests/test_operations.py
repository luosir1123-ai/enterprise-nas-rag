from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "apps" / "internal-portal" / "backend"))

from app.ops_status import evaluation_status, sync_status  # noqa: E402
from business_metadata import infer_business_metadata  # noqa: E402
from nas_sync_policy import missing_document_action, prioritize_changes  # noqa: E402
from ragflow_business_acceptance import load_cases, required_term_matches, score_case  # noqa: E402


class NasSyncPolicyTests(unittest.TestCase):
    def test_legacy_and_current_missing_documents_are_distinguished(self) -> None:
        source_id = "synology-192.0.2.90"
        legacy = {"source_generation": "legacy", "sync_status": "historical"}
        current = {"source_generation": "current", "source_nas_id": source_id, "sync_status": "active"}
        current_missing = {**current, "sync_status": "missing_from_source"}

        self.assertIsNone(missing_document_action(legacy, source_id))
        self.assertEqual(missing_document_action({}, source_id), "mark_legacy")
        self.assertEqual(missing_document_action(current, source_id), "mark_missing")
        self.assertIsNone(missing_document_action(current_missing, source_id))

    def test_content_changes_are_prioritized_over_metadata_migration(self) -> None:
        changes = [
            {"action": "mark_legacy", "kb_key": "purchase"},
            {"action": "metadata_refresh", "kb_key": "purchase"},
            {"action": "added", "kb_key": "product"},
            {"action": "modified", "kb_key": "sales"},
        ]
        ordered = prioritize_changes(changes)
        self.assertEqual([item["action"] for item in ordered], ["modified", "added", "metadata_refresh", "mark_legacy"])


class BusinessMetadataTests(unittest.TestCase):
    def test_catalog_metadata_is_inferred_from_path(self) -> None:
        metadata = infer_business_metadata("Catalog/2025 Spring Catalog/LT-W80报价.xlsx", "sales")
        self.assertEqual(metadata["year"], "2025")
        self.assertEqual(metadata["season"], "spring")
        self.assertEqual(metadata["document_type"], "quotation")
        self.assertIn("LT-W80", metadata["models"])
        self.assertEqual(metadata["authority_price"], 100)

    def test_specification_has_high_technical_authority(self) -> None:
        metadata = infer_business_metadata("产品规格书/PT-978产品规格书.pdf", "product_design")
        self.assertEqual(metadata["document_type"], "specification")
        self.assertEqual(metadata["authority_technical"], 100)
        self.assertLess(metadata["authority_price"], metadata["authority_technical"])

    def test_filename_date_wins_and_certification_acronyms_are_not_models(self) -> None:
        metadata = infer_business_metadata("2025报价/A10/2024010907718272 CE-EMC.pdf", "purchase")
        self.assertEqual(metadata["year"], "2024")
        self.assertNotIn("CE-EMC", metadata["models"])

    def test_dotted_month_is_extracted(self) -> None:
        metadata = infer_business_metadata("报价/商务键盘-2025.10.pdf", "purchase")
        self.assertEqual(metadata["year"], "2025")
        self.assertEqual(metadata["month"], "10")


class OperationsStatusTests(unittest.TestCase):
    def test_latest_sync_and_evaluation_reports_are_summarized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sync_run = root / "sync" / "20260722_010000"
            eval_run = root / "eval" / "20260722_020000"
            sync_run.mkdir(parents=True)
            eval_run.mkdir(parents=True)
            (sync_run / "report.json").write_text(
                json.dumps(
                    {
                        "started_at": "2026-07-22 01:00:00",
                        "finished_at": "2026-07-22 01:00:10",
                        "source_nas_name": "LeTouch NAS 2026",
                        "apply": True,
                        "parse": True,
                        "applied_count": 3,
                        "changes": [{}, {}, {}],
                        "deferred": [{}],
                        "errors": [],
                        "datasets": [
                            {
                                "kb_key": "purchase",
                                "name": "采购知识库",
                                "current_candidates": 10,
                                "ragflow_documents": 20,
                                "counts": {"unchanged": 9, "added": 1, "legacy_retained": 10},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (eval_run / "report.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-22 02:00:00",
                        "case_count": 5,
                        "passed": 4,
                        "failed": 1,
                        "pass_rate": 0.8,
                        "error_count": 0,
                        "suites": [{"name": "source_coverage", "case_count": 5, "passed": 4, "failed": 1, "pass_rate": 0.8}],
                        "knowledge_bases": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            sync = sync_status(str(root / "sync"))
            evaluation = evaluation_status(str(root / "eval"))
            self.assertEqual(sync["state"], "pending")
            self.assertEqual(sync["datasets"][0]["historical_retained"], 10)
            self.assertEqual(evaluation["state"], "failed")
            self.assertEqual(evaluation["pass_rate"], 0.8)


class EvaluationCaseTests(unittest.TestCase):
    def test_template_schema_is_normalized_and_source_is_scored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.csv"
            path.write_text(
                "question,expected_answer,source_file,source_section_or_page,knowledge_base,must_refuse_if_no_evidence\n"
                "型号是什么,答案,PUR-SHR/规格书/OL-209.docx,第一章,采购知识库,false\n",
                encoding="utf-8",
            )
            case = load_cases([f"coverage={path}"])[0]
            self.assertEqual(case["expected_source_file"], "OL-209.docx")
            score = score_case(
                case,
                {"answer": "型号是 OL-209", "reference": {"chunks": [{"doc_name": "OL-209.docx"}]}},
            )
            self.assertTrue(score["passed"])

    def test_numeric_terms_treat_decimal_format_as_equivalent(self) -> None:
        self.assertTrue(required_term_matches("12W", "支持 12.0W、15.0W 和 17.0W 三档功率"))
        self.assertFalse(required_term_matches("12V", "支持 12.0W 输出功率"))

    def test_semantic_safe_refusal_is_accepted(self) -> None:
        case = {
            "must_refuse": "true",
            "required_terms": "",
            "expected_source_file": "",
        }
        score = score_case(case, {"answer": "未找到相关数据。", "reference": {}})
        self.assertTrue(score["passed"])
        self.assertEqual(score["scorer_version"], "v2")

    def test_scoring_exposes_retrieval_and_answer_dimensions(self) -> None:
        case = {
            "must_refuse": "false",
            "required_terms": "12W|15W|17W",
            "expected_source_file": "OL-209.xlsx",
        }
        score = score_case(
            case,
            {
                "answer": "输出档位为 12.0W、15.0W、17.0W。",
                "reference": {"chunks": [{"doc_name": "OL-209.xlsx"}]},
            },
        )
        self.assertTrue(score["passed"])
        self.assertTrue(score["target_document_recalled"])
        self.assertTrue(score["answer_terms_pass"])


if __name__ == "__main__":
    unittest.main()
