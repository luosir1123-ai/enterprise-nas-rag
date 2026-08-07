"""Pure policy helpers for reconciling legacy and current NAS documents."""

from __future__ import annotations

from collections.abc import Iterable


ACTION_PRIORITY = {
    "modified": 0,
    "added": 1,
    "mark_missing": 2,
    "metadata_refresh": 3,
    "mark_legacy": 4,
}


def is_current_source(metadata: dict, source_id: str) -> bool:
    return (
        metadata.get("source_nas_id") == source_id
        and metadata.get("source_generation") == "current"
    )


def is_classified_legacy(metadata: dict) -> bool:
    return (
        metadata.get("source_generation") == "legacy"
        and metadata.get("sync_status") == "historical"
    )


def missing_document_action(metadata: dict, source_id: str) -> str | None:
    """Return a non-destructive lifecycle action for a document absent on the current NAS."""
    if is_current_source(metadata, source_id):
        if metadata.get("sync_status") == "missing_from_source":
            return None
        return "mark_missing"
    if is_classified_legacy(metadata):
        return None
    return "mark_legacy"


def prioritize_changes(changes: Iterable[dict]) -> list[dict]:
    """Process content changes before background metadata migration."""
    return sorted(
        changes,
        key=lambda item: (
            ACTION_PRIORITY.get(str(item.get("action")), 99),
            str(item.get("kb_key", "")),
            str(item.get("relative_path", "")),
            str(item.get("document_id", "")),
        ),
    )
