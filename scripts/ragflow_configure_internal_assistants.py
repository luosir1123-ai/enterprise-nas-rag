"""Apply the shared retrieval and refusal policy to internal RAGFlow chats."""

from __future__ import annotations

import json

from api.db.services.dialog_service import DialogService
from common import settings

from ragflow_env import get_target_tenant_id


CHAT_CONFIGS = (
    ("\u91c7\u8d2d\u52a9\u624b", True),
    ("\u9500\u552e\u52a9\u7406", True),
    ("\u4ea7\u54c1\u8bbe\u8ba1", False),
)
REFUSAL_TEXT = "\u5f53\u524d\u77e5\u8bc6\u5e93\u6ca1\u6709\u8db3\u591f\u8bc1\u636e\u652f\u6301\u8be5\u95ee\u9898\u3002"
SYSTEM_PROMPT = """
You are an internal enterprise knowledge assistant. Answer only from the
retrieved knowledge below. Preserve product model numbers, dates, units,
    prices, quantities, currencies, certification names, and table row
    relationships exactly. Distinguish facts from different files and versions.
    For technical facts prefer sources with higher authority_technical; for
    quotes and purchase prices prefer higher authority_price; for catalog costs
    prefer higher authority_sales_cost. If equally authoritative sources
    conflict, list each value with its file and version and explicitly state the
    conflict instead of silently choosing one.
    Always cite the supplied sources. If the retrieved knowledge does not directly
prove the requested fact, return exactly the configured empty response. Do not
infer or invent missing values, and do not cite unrelated sources on refusal.

Knowledge:
{knowledge}

Answer in Chinese. Keep the response concise unless the user asks for a table
or comparison.
""".strip()


def main() -> None:
    settings.init_settings()
    tenant_id = get_target_tenant_id()
    updated = []

    for name, model_doc_prefilter in CHAT_CONFIGS:
        matches = DialogService.query(tenant_id=tenant_id, name=name, status="1")
        if not matches:
            raise RuntimeError(f"chat not found: {name}")
        dialog = matches[0]
        prompt_config = dict(dialog.prompt_config or {})
        prompt_config.update(
            {
                "system": SYSTEM_PROMPT,
                "quote": True,
                "reasoning": False,
                "keyword": False,
                "use_kg": False,
                "document_name_prefilter": True,
                "model_doc_prefilter": model_doc_prefilter,
                "excel_row_prefilter": model_doc_prefilter,
                "excel_row_evidence": model_doc_prefilter,
                "excel_row_evidence_limit": 8,
                "authority_rerank": True,
                "authority_weight": 0.18,
                "reference_metadata": {
                    "include": True,
                    "fields": [
                        "nas_relative_path",
                        "document_type",
                        "model",
                        "models",
                        "year",
                        "month",
                        "season",
                        "business_version",
                        "effective_status",
                        "source_version",
                        "authority_technical",
                        "authority_price",
                        "authority_sales_cost",
                    ],
                },
                "empty_response": REFUSAL_TEXT,
                "parameters": [{"key": "knowledge", "optional": False}],
            }
        )
        changes = {
            "prompt_config": prompt_config,
            "top_n": 12,
            "top_k": 256,
            "similarity_threshold": 0.15,
            "vector_similarity_weight": 0.55,
        }
        DialogService.update_by_id(dialog.id, changes)
        updated.append(
            {
                "id": dialog.id,
                "name": name,
                "kb_ids": dialog.kb_ids,
                "model_doc_prefilter": model_doc_prefilter,
                "excel_row_prefilter": model_doc_prefilter,
                "document_name_prefilter": True,
                "authority_rerank": True,
                "empty_response": REFUSAL_TEXT,
            }
        )

    print(json.dumps({"updated": updated}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
