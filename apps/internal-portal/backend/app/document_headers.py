from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import quote


def _safe_filename(name: str) -> str:
    filename = str(name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    filename = "".join(char for char in filename if ord(char) >= 32 and char not in "\r\n")
    return filename or "document"


def _ascii_fallback(filename: str) -> str:
    fallback = "".join(
        char if 32 <= ord(char) < 127 and char not in {'"', "\\"} else "_"
        for char in filename
    )
    fallback = re.sub(r"_+", "_", fallback).strip(" ._")
    if fallback:
        return fallback
    extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
    return f"document.{extension}" if extension.isascii() and extension else "document"


def _document_response_headers(
    upstream_headers: Mapping[str, str],
    filename: str,
    *,
    download: bool,
) -> dict[str, str]:
    safe_filename = _safe_filename(filename)
    disposition = "attachment" if download else "inline"
    headers = {
        "content-disposition": (
            f'{disposition}; filename="{_ascii_fallback(safe_filename)}"; '
            f"filename*=UTF-8''{quote(safe_filename, safe='')}"
        )
    }
    for header_name in ("content-type", "x-content-type-options"):
        value = upstream_headers.get(header_name)
        if value:
            try:
                value.encode("latin-1")
            except UnicodeEncodeError:
                continue
            headers[header_name] = value
    return headers
