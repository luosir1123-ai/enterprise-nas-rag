"""Run a non-streaming smoke test for the configured RAGFlow chat app."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from api.db.services.dialog_service import DialogService, async_chat
from common import settings


CHAT_ID = "5dc6373c746011f1b4e439a2bb3fe40b"


async def main() -> None:
    if settings.docStoreConn is None:
        settings.init_settings()

    ok, dialog = DialogService.get_by_id(CHAT_ID)
    if not ok:
        raise RuntimeError(f"Chat not found: {CHAT_ID}")

    messages = [
        {"role": "assistant", "content": dialog.prompt_config.get("prologue", "")},
        {
            "role": "user",
            "content": "LT-G20\u5927\u7406\u77f3 \u5355\u4ef7\u591a\u5c11\uff1f",
        },
    ]

    answer = None
    async for item in async_chat(dialog, messages, stream=False, session_id="codex-smoke-test"):
        answer = item
        break

    out = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "chat_id": CHAT_ID,
        "chat_name": dialog.name,
        "kb_ids": dialog.kb_ids,
        "question": messages[-1]["content"],
        "answer": answer,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
