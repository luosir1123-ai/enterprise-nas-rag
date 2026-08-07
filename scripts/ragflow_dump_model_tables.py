"""Dump model-related RAGFlow database tables with secrets masked.

Run inside the RAGFlow container with /ragflow as the working directory.
Read-only diagnostic script.
"""

from __future__ import annotations

import json
from datetime import datetime

from api.db import db_models


SECRET_HINTS = ("key", "secret", "token", "password", "passwd", "credential")


def is_secret(name: str) -> bool:
    return any(hint in name.lower() for hint in SECRET_HINTS)


def value_to_json(value):
    if value is None:
        return None
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def row_to_dict(row) -> dict:
    data = {}
    for field in row._meta.sorted_fields:
        name = field.name
        if is_secret(name):
            raw = getattr(row, name)
            data[name] = "***masked***" if raw else raw
        else:
            data[name] = value_to_json(getattr(row, name))
    return data


def main() -> None:
    out = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tables": {},
    }

    for name in sorted(dir(db_models)):
        if not any(token in name.lower() for token in ["llm", "model", "provider", "tenant"]):
            continue
        cls = getattr(db_models, name)
        meta = getattr(cls, "_meta", None)
        if meta is None or not getattr(meta, "sorted_fields", None):
            continue
        try:
            count = cls.select().count()
            rows = [row_to_dict(row) for row in cls.select().limit(10)]
            fields = [field.name for field in meta.sorted_fields]
            out["tables"][name] = {
                "table_name": meta.table_name,
                "count": count,
                "fields": fields,
                "sample_rows": rows,
            }
        except Exception as exc:  # noqa: BLE001
            out["tables"][name] = {
                "table_name": getattr(meta, "table_name", None),
                "error": repr(exc),
            }

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
