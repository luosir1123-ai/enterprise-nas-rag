"""List RAGFlow model-related database records.

Run inside the RAGFlow container with /ragflow as the working directory.
Read-only script for diagnosing which LLM providers and model IDs are already
configured for the current tenant.
"""

from __future__ import annotations

import json
from datetime import datetime

from api.db import db_models
from ragflow_env import get_target_tenant_id


def model_to_dict(obj) -> dict:
    data = {}
    for field in obj._meta.sorted_fields:
        name = field.name
        if name.lower() in {"api_key", "secret_key", "access_key", "ak", "sk"}:
            data[name] = "***masked***"
            continue
        value = getattr(obj, name)
        try:
            json.dumps(value)
            data[name] = value
        except TypeError:
            data[name] = str(value)
    return data


def query_model(model_cls, **filters) -> list[dict]:
    try:
        query = model_cls.select()
        for key, value in filters.items():
            query = query.where(getattr(model_cls, key) == value)
        return [model_to_dict(item) for item in query]
    except Exception as exc:  # noqa: BLE001
        return [{"error": repr(exc), "model": model_cls.__name__}]


def main() -> None:
    tenant_id = get_target_tenant_id()
    available = sorted(
        name
        for name in dir(db_models)
        if any(token in name.lower() for token in ["llm", "tenant", "dialog", "model"])
    )

    output = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tenant_id": tenant_id,
        "available_model_classes": available,
        "records": {},
    }

    for class_name in [
        "Tenant",
        "TenantLLM",
        "TenantModelProvider",
        "TenantModelInstance",
        "TenantModel",
        "TenantModelGroup",
        "TenantModelGroupMapping",
        "LLMFactories",
        "LLM",
        "Dialog",
        "Conversation",
    ]:
        model_cls = getattr(db_models, class_name, None)
        if model_cls is None:
            output["records"][class_name] = [{"missing_model_class": True}]
            continue

        if class_name in {"Tenant", "TenantLLM", "TenantModelProvider", "Dialog"}:
            output["records"][class_name] = query_model(model_cls, tenant_id=tenant_id)
        else:
            output["records"][class_name] = query_model(model_cls)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
