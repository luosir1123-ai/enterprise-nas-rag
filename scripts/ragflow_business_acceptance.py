"""Run source coverage, answer accuracy, citation, and refusal tests in RAGFlow.

The script runs inside the RAGFlow container and changes no persisted dialog or
dataset settings. Repeat ``--cases`` to combine multiple named test suites.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import traceback
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path


DATASET_IDS = {
    "\u91c7\u8d2d\u77e5\u8bc6\u5e93": "<configure-purchase-dataset-id>",
    "\u9500\u552e\u77e5\u8bc6\u5e93": "<configure-sales-dataset-id>",
    "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u8bc6\u5e93": "<configure-product-dataset-id>",
}
CHAT_IDS = {
    "\u91c7\u8d2d\u77e5\u8bc6\u5e93": "<configure-purchase-chat-id>",
    "\u9500\u552e\u77e5\u8bc6\u5e93": "<configure-sales-chat-id>",
    "\u4ea7\u54c1\u8bbe\u8ba1\u77e5\u5e93": "<configure-product-chat-id>",
}
REFUSAL_TEXT = "\u5f53\u524d\u77e5\u8bc6\u5e93\u6ca1\u6709\u8db3\u591f\u8bc1\u636e\u652f\u6301\u8be5\u95ee\u9898\u3002"
SCORER_VERSION = "v2"
REFUSAL_PATTERN = re.compile(
    r"(?:\u6ca1\u6709|\u672a|\u6682\u672a).{0,16}(?:\u8bc1\u636e|\u4fe1\u606f|\u8d44\u6599|\u627e\u5230|\u68c0\u7d22\u5230|\u76f8\u5173\u6570\u636e)|"
    r"\u5f53\u524d\u77e5\u8bc6\u5e93.{0,8}\u6ca1\u6709.*(?:\u4fe1\u606f|\u8d44\u6599|\u8bc1\u636e)|"
    r"\u65e0\u6cd5(?:\u56de\u7b54|\u63d0\u4f9b|\u786e\u5b9a)|"
    r"(?:\u8bc1\u636e|\u4fe1\u606f|\u8d44\u6599)(?:\u4e0d\u8db3|\u4e0d\u591f)|"
    r"\u4e0d\u8db3\u4ee5(?:\u56de\u7b54|\u8bc1\u660e)",
    re.IGNORECASE,
)
CITATION_PATTERN = re.compile(r"\[(?:ID:)?\d+\]", re.IGNORECASE)
MEASUREMENT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9.])([+-]?\d+(?:\.\d+)?)\s*"
    r"(mah|wh|kw|mw|w|kv|mv|v|ma|a|mm|cm|kg|g|pcs?|%|元|块)",
    re.IGNORECASE,
)
SYSTEM_PROMPT = """
You are an internal enterprise knowledge-base assistant. Answer only from the
retrieved knowledge below. Preserve model numbers, units, prices, quantities,
and table row relationships exactly. Cite the supplied sources. If the
question explicitly names a source file, summarize that file's relevant or
core content and cite it; do not refuse merely because the requested business
framing is absent. If the retrieved knowledge does not directly prove the
requested fact, return exactly: 当前知识库没有足够证据支持该问题。 Do not infer,
invent, or cite unrelated sources on refusal.

Knowledge:
{knowledge}

Answer in Chinese and keep the answer concise.
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        action="append",
        required=True,
        metavar="[SUITE=]CSV",
        help="CSV case file; repeat to combine coverage and business suites",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--chat-id", default="", help="Optional assistant override for diagnostics")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--case-timeout", type=int, default=120)
    return parser.parse_args()


def normalize(text: str) -> str:
    return re.sub(r"[\s,，：:；;（）()\[\]]+", "", (text or "").lower())


def extract_measurements(text: str) -> list[tuple[float, str]]:
    measurements = []
    for match in MEASUREMENT_PATTERN.finditer(str(text or "")):
        measurements.append((float(match.group(1)), match.group(2).casefold()))
    return measurements


def required_term_matches(term: str, answer_text: str, answer_norm: str | None = None) -> bool:
    answer_norm = answer_norm if answer_norm is not None else normalize(answer_text)
    if normalize(term) in answer_norm:
        return True
    expected_measurements = extract_measurements(term)
    if not expected_measurements:
        return False
    actual_measurements = extract_measurements(answer_text)
    return all(
        any(abs(expected_value - actual_value) < 1e-9 and expected_unit == actual_unit for actual_value, actual_unit in actual_measurements)
        for expected_value, expected_unit in expected_measurements
    )


def extract_reference_names(answer: dict) -> list[str]:
    names = []
    reference = answer.get("reference") or {}
    chunks = reference.get("chunks") if isinstance(reference, dict) else reference
    for chunk in chunks or []:
        name = chunk.get("doc_name") or chunk.get("docnm_kwd") or chunk.get("document_name")
        if name and name not in names:
            names.append(name)
    return names


def bool_text(value: str) -> str:
    return "true" if str(value or "").strip().lower() in {"1", "true", "yes", "y"} else "false"


def source_basename(value: str) -> str:
    return str(value or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def load_cases(specs: list[str]) -> list[dict]:
    cases = []
    for spec in specs:
        if "=" in spec:
            suite, path_text = spec.split("=", 1)
        else:
            path_text = spec
            suite = Path(path_text).stem
        path = Path(path_text)
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        for index, row in enumerate(rows, start=1):
            knowledge_base = str(row.get("knowledge_base") or "").strip()
            if knowledge_base not in DATASET_IDS:
                raise ValueError(f"unknown knowledge base in {path}: {knowledge_base}")
            question = str(row.get("question") or "").strip()
            if not question:
                raise ValueError(f"empty question in {path} row {index}")
            cases.append(
                {
                    "suite": suite,
                    "case_id": str(row.get("case_id") or f"{suite}-{index:03d}"),
                    "knowledge_base": knowledge_base,
                    "question": question,
                    "expected_answer": str(row.get("expected_answer") or "").strip(),
                    "expected_source_file": source_basename(
                        str(row.get("expected_source_file") or row.get("source_file") or "")
                    ),
                    "required_terms": str(row.get("required_terms") or "").strip(),
                    "must_refuse": bool_text(
                        str(row.get("must_refuse") or row.get("must_refuse_if_no_evidence") or "")
                    ),
                }
            )
    return cases


def score_case(case: dict, answer: dict) -> dict:
    answer_text = answer.get("answer") or ""
    reference_names = extract_reference_names(answer)
    must_refuse = case["must_refuse"].strip().lower() == "true"
    required_terms = [term for term in case["required_terms"].split("|") if term]
    answer_norm = normalize(answer_text)
    missing_terms = [
        term for term in required_terms if not required_term_matches(term, answer_text, answer_norm)
    ]

    if must_refuse:
        refusal_pass = bool(REFUSAL_PATTERN.search(answer_text))
        no_answer_citation = not bool(CITATION_PATTERN.search(answer_text))
        passed = refusal_pass and no_answer_citation
        return {
            "passed": passed,
            "scorer_version": SCORER_VERSION,
            "refusal_pass": refusal_pass,
            "no_citation_on_refusal": no_answer_citation,
            "missing_terms": [],
            "expected_source_pass": True,
            "target_document_recalled": None,
            "answer_terms_pass": None,
            "reference_names": reference_names,
        }

    expected_source = case["expected_source_file"]
    source_pass = bool(expected_source) and any(
        expected_source.lower() in name.lower() for name in reference_names
    )
    terms_pass = not missing_terms
    return {
        "passed": source_pass and terms_pass,
        "scorer_version": SCORER_VERSION,
        "refusal_pass": None,
        "no_citation_on_refusal": None,
        "missing_terms": missing_terms,
        "expected_source_pass": source_pass,
        "target_document_recalled": source_pass,
        "answer_terms_pass": terms_pass,
        "reference_names": reference_names,
    }


async def run_case(base_dialog, case: dict) -> dict:
    from api.db.services.dialog_service import async_chat

    dialog = deepcopy(base_dialog)
    dialog.kb_ids = [DATASET_IDS[case["knowledge_base"]]]
    dialog.prompt_config = deepcopy(dialog.prompt_config or {})
    dialog.prompt_config.update(
        {
            "system": SYSTEM_PROMPT,
            "quote": True,
            "use_kg": False,
            "reasoning": False,
            "keyword": False,
            "parameters": [{"key": "knowledge", "optional": False}],
            "empty_response": REFUSAL_TEXT,
        }
    )
    dialog.do_refer = "1"
    dialog.top_n = 12
    dialog.top_k = 256
    dialog.similarity_threshold = 0.15
    dialog.vector_similarity_weight = 0.55

    messages = [
        {"role": "assistant", "content": ""},
        {"role": "user", "content": case["question"]},
    ]
    answer = None
    async for item in async_chat(
        dialog,
        messages,
        stream=False,
        session_id=f"acceptance-{case['case_id']}-{uuid.uuid4().hex[:8]}",
        internet=False,
    ):
        answer = item
        if item.get("final", True):
            break
    if answer is None:
        answer = {"answer": "", "reference": {}}

    score = score_case(case, answer)
    return {
        **case,
        **score,
        "answer": answer.get("answer") or "",
        "reference": answer.get("reference") or {},
    }


def grouped_summary(results: list[dict], field: str) -> list[dict]:
    names = list(dict.fromkeys(str(result.get(field) or "") for result in results))
    summaries = []
    for name in names:
        grouped = [result for result in results if str(result.get(field) or "") == name]
        passed = sum(1 for result in grouped if result.get("passed"))
        summaries.append(
            {
                "name": name,
                "case_count": len(grouped),
                "passed": passed,
                "failed": len(grouped) - passed,
                "pass_rate": round(passed / len(grouped), 4) if grouped else 0,
            }
        )
    return summaries


async def main() -> None:
    from common import settings
    from api.db.services.dialog_service import DialogService

    args = parse_args()
    if settings.docStoreConn is None:
        settings.init_settings()
    cases = load_cases(args.cases)
    dialogs = {}
    for knowledge_base in DATASET_IDS:
        chat_id = args.chat_id or CHAT_IDS[knowledge_base]
        ok, dialog = DialogService.get_by_id(chat_id)
        if not ok:
            raise RuntimeError(f"chat not found: {chat_id}")
        dialogs[knowledge_base] = dialog

    semaphore = asyncio.Semaphore(max(args.concurrency, 1))

    async def evaluate(index: int, case: dict) -> dict:
        async with semaphore:
            print(
                f"[{index}/{len(cases)}] start {case['suite']} {case['case_id']} ",
                f"{case['knowledge_base']}",
                flush=True,
            )
            try:
                result = await asyncio.wait_for(
                    run_case(dialogs[case["knowledge_base"]], case),
                    timeout=max(args.case_timeout, 10),
                )
            except Exception as exc:
                result = {
                    **case,
                    "passed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                }
            print(
                f"[{index}/{len(cases)}] done passed={bool(result.get('passed'))} ",
                f"error={result.get('error', '')}",
                flush=True,
            )
            return result

    results = await asyncio.gather(
        *(evaluate(index, case) for index, case in enumerate(cases, start=1))
    )

    passed = sum(1 for result in results if result.get("passed"))
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scorer_version": SCORER_VERSION,
        "chat_models": {
            knowledge_base: dialog.llm_id for knowledge_base, dialog in dialogs.items()
        },
        "embedding_by_dataset": {
            "purchase": "text-embedding-v4",
            "sales": "text-embedding-v4",
            "product_design": "text-embedding-v4",
        },
        "case_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "error_count": sum(1 for result in results if result.get("error")),
        "pass_rate": round(passed / len(results), 4) if results else 0,
        "suites": grouped_summary(results, "suite"),
        "knowledge_bases": grouped_summary(results, "knowledge_base"),
        "results": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
