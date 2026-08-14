"""Switch the current RAGFlow chat app to a local Ollama chat model.

Run inside the RAGFlow container with /ragflow as the working directory.
This script keeps embeddings unchanged and updates only the tenant/dialog chat
LLM record for the existing Ollama provider instance.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from api.db.services.conversation_service import ConversationService
from api.db.services.dialog_service import DialogService
from api.db.services.tenant_llm_service import TenantService
from api.db.services.tenant_model_instance_service import TenantModelInstanceService
from api.db.services.tenant_model_provider_service import TenantModelProviderService
from api.db.services.tenant_model_service import TenantModelService
from common.constants import LLMType


TENANT_ID = "<configure-RAGFLOW_TENANT_ID>"
CHAT_ID = "<configure-RAGFLOW_CHAT_ID>"
PROVIDER_NAME = "Ollama"
INSTANCE_NAME = "local-ollama"


def ensure_ollama_chat_model(model_name: str, max_tokens: int) -> dict:
    provider = TenantModelProviderService.get_by_tenant_id_and_provider_name(
        TENANT_ID,
        PROVIDER_NAME,
    )
    if not provider:
        raise RuntimeError("Ollama provider not found")

    instance = TenantModelInstanceService.get_by_provider_id_and_instance_name(
        provider.id,
        INSTANCE_NAME,
    )
    if not instance:
        raise RuntimeError("local-ollama instance not found")

    model = TenantModelService.get_by_provider_id_and_instance_id_and_model_type_and_model_name(
        provider.id,
        instance.id,
        LLMType.CHAT.value,
        model_name,
    )
    if not model:
        TenantModelService.insert(
            model_name=model_name,
            provider_id=provider.id,
            instance_id=instance.id,
            model_type=LLMType.CHAT.value,
            status="active",
            extra=json.dumps({"max_tokens": max_tokens, "is_tools": True}),
        )
        model = TenantModelService.get_by_provider_id_and_instance_id_and_model_type_and_model_name(
            provider.id,
            instance.id,
            LLMType.CHAT.value,
            model_name,
        )
        if not model:
            raise RuntimeError("Failed to create Ollama chat model record")
    else:
        TenantModelService.update_by_id(
            model.id,
            {
                "status": "active",
                "extra": json.dumps({"max_tokens": max_tokens, "is_tools": True}),
            },
        )
        model = TenantModelService.get_by_provider_id_and_instance_id_and_model_type_and_model_name(
            provider.id,
            instance.id,
            LLMType.CHAT.value,
            model_name,
        )

    return {
        "provider_id": provider.id,
        "instance_id": instance.id,
        "model_record_id": model.id,
        "model_id": f"{model_name}@{INSTANCE_NAME}@{PROVIDER_NAME}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5:0.5b")
    parser.add_argument("--max-tokens", type=int, default=32768)
    args = parser.parse_args()

    ok, dialog = DialogService.get_by_id(CHAT_ID)
    if not ok:
        raise RuntimeError(f"Chat not found: {CHAT_ID}")

    tenant_ok, tenant = TenantService.get_by_id(TENANT_ID)
    if not tenant_ok:
        raise RuntimeError(f"Tenant not found: {TENANT_ID}")

    before = {
        "tenant_llm_id": tenant.llm_id,
        "chat_llm_id": dialog.llm_id,
    }
    model_info = ensure_ollama_chat_model(args.model, args.max_tokens)
    model_id = model_info["model_id"]

    llm_setting = dialog.llm_setting or {}
    llm_setting.update(
        {
            "temperature": 0.1,
            "top_p": 0.8,
            "presence_penalty": 0.1,
            "frequency_penalty": 0.1,
            "max_tokens": 512,
        }
    )

    if not TenantService.update_by_id(TENANT_ID, {"llm_id": model_id}):
        raise RuntimeError("Failed to update tenant default LLM")

    if not DialogService.update_by_id(
        CHAT_ID,
        {
            "llm_id": model_id,
            "tenant_llm_id": None,
            "llm_setting": llm_setting,
        },
    ):
        raise RuntimeError("Failed to update dialog LLM")

    reset_sessions = []
    for conv in ConversationService.query(dialog_id=CHAT_ID):
        if conv.name:
            reset_sessions.append(conv.id)
            ConversationService.update_by_id(
                conv.id,
                {
                    "message": [
                        {
                            "role": "assistant",
                            "content": (dialog.prompt_config or {}).get(
                                "prologue",
                                "Hi! I'm your assistant. What can I do for you?",
                            ),
                        }
                    ],
                    "reference": [],
                },
            )

    ok, dialog_after = DialogService.get_by_id(CHAT_ID)
    tenant_ok, tenant_after = TenantService.get_by_id(TENANT_ID)
    out = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "before": before,
        "after": {
            "tenant_llm_id": tenant_after.llm_id if tenant_ok else None,
            "chat_llm_id": dialog_after.llm_id if ok else None,
        },
        "model": model_info,
        "reset_sessions": reset_sessions,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
