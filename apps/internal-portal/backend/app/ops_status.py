"""Read-only operational status summaries for the internal portal."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any


def _latest_report(root: str) -> tuple[dict[str, Any] | None, Path | None]:
    directory = Path(root)
    if not directory.is_dir():
        return None, None
    reports = sorted(
        directory.glob("*/report.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in reports:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value, path
    return None, None


def _age_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        moment = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return max(int((datetime.now() - moment).total_seconds()), 0)


def sync_status(root: str) -> dict[str, Any]:
    report, path = _latest_report(root)
    if report is None:
        return {"available": False, "state": "unavailable", "datasets": []}

    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    deferred = report.get("deferred") if isinstance(report.get("deferred"), list) else []
    finished_at = report.get("finished_at")
    datasets = []
    for dataset in report.get("datasets") or []:
        if not isinstance(dataset, dict):
            continue
        counts = dataset.get("counts") if isinstance(dataset.get("counts"), dict) else {}
        datasets.append(
            {
                "key": dataset.get("kb_key"),
                "name": dataset.get("name"),
                "current_candidates": int(dataset.get("current_candidates") or 0),
                "ragflow_documents": int(dataset.get("ragflow_documents") or 0),
                "unchanged": int(counts.get("unchanged") or 0),
                "added": int(counts.get("added") or 0),
                "modified": int(counts.get("modified") or 0),
                "metadata_refresh": int(counts.get("metadata_refresh") or 0),
                "duplicate_current_path": int(counts.get("duplicate_current_path") or 0),
                "historical_retained": int(counts.get("legacy_retained") or 0),
                "missing_from_source": int(counts.get("missing_from_current_source") or 0),
            }
        )

    if not finished_at:
        state = "running"
    elif errors:
        state = "error"
    elif deferred:
        state = "pending"
    else:
        state = "healthy"

    return {
        "available": True,
        "state": state,
        "started_at": report.get("started_at"),
        "finished_at": finished_at,
        "age_seconds": _age_seconds(finished_at or report.get("started_at")),
        "source_nas_name": report.get("source_nas_name") or "NAS",
        "deletion_policy": report.get("deletion_policy") or "report_only",
        "apply": bool(report.get("apply")),
        "parse": bool(report.get("parse")),
        "applied_count": int(report.get("applied_count") or 0),
        "pending_count": len(deferred),
        "error_count": len(errors),
        "change_count": len(report.get("changes") or []),
        "datasets": datasets,
        "run_id": path.parent.name if path else None,
    }


def evaluation_status(root: str) -> dict[str, Any]:
    report, path = _latest_report(root)
    if report is None:
        return {"available": False, "state": "unavailable", "suites": [], "knowledge_bases": []}

    failed = int(report.get("failed") or 0)
    errors = int(report.get("error_count") or 0)
    state = "healthy" if failed == 0 and errors == 0 else "failed"
    return {
        "available": True,
        "state": state,
        "generated_at": report.get("generated_at"),
        "age_seconds": _age_seconds(report.get("generated_at")),
        "case_count": int(report.get("case_count") or 0),
        "passed": int(report.get("passed") or 0),
        "failed": failed,
        "pass_rate": float(report.get("pass_rate") or 0),
        "error_count": errors,
        "suites": report.get("suites") if isinstance(report.get("suites"), list) else [],
        "knowledge_bases": (
            report.get("knowledge_bases")
            if isinstance(report.get("knowledge_bases"), list)
            else []
        ),
        "run_id": path.parent.name if path else None,
    }
