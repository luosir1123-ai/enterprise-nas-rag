from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid


class HistoryStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    owner_key TEXT NOT NULL,
                    assistant_id TEXT NOT NULL,
                    session_id TEXT,
                    title TEXT NOT NULL,
                    messages_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_owner_assistant
                    ON conversations(owner_key, assistant_id, updated_at DESC);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def list(self, owner_key: str, assistant_id: str, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, assistant_id, session_id, title, messages_json, created_at, updated_at
                FROM conversations
                WHERE owner_key = ? AND assistant_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (owner_key, assistant_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._summary(row) for row in rows]

    def get(self, owner_key: str, conversation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, assistant_id, session_id, title, messages_json, created_at, updated_at
                FROM conversations
                WHERE owner_key = ? AND id = ?
                """,
                (owner_key, conversation_id),
            ).fetchone()
        return self._record(row) if row else None

    def upsert(
        self,
        owner_key: str,
        assistant_id: str,
        conversation_id: str | None,
        session_id: str | None,
        title: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        record_id = conversation_id or uuid.uuid4().hex
        normalized_title = (title or "新对话").strip()[:120] or "新对话"
        encoded_messages = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM conversations WHERE owner_key = ? AND id = ?",
                (owner_key, record_id),
            ).fetchone()
            created_at = str(existing["created_at"]) if existing else now
            connection.execute(
                """
                INSERT INTO conversations
                    (id, owner_key, assistant_id, session_id, title, messages_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    session_id = excluded.session_id,
                    title = excluded.title,
                    messages_json = excluded.messages_json,
                    updated_at = excluded.updated_at
                """,
                (record_id, owner_key, assistant_id, session_id, normalized_title, encoded_messages, created_at, now),
            )
        return {
            "id": record_id,
            "assistant_id": assistant_id,
            "session_id": session_id,
            "title": normalized_title,
            "messages": messages,
            "created_at": created_at,
            "updated_at": now,
        }

    @staticmethod
    def _decoded_messages(row: sqlite3.Row) -> list[dict[str, Any]]:
        try:
            value = json.loads(str(row["messages_json"]))
        except (TypeError, json.JSONDecodeError):
            return []
        return value if isinstance(value, list) else []

    @classmethod
    def _summary(cls, row: sqlite3.Row) -> dict[str, Any]:
        messages = cls._decoded_messages(row)
        user_messages = [item for item in messages if item.get("role") == "user"]
        preview = str(user_messages[0].get("content", ""))[:160] if user_messages else str(row["title"])
        return {
            "id": row["id"],
            "assistant_id": row["assistant_id"],
            "session_id": row["session_id"],
            "title": row["title"],
            "preview": preview,
            "message_count": len(messages),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @classmethod
    def _record(cls, row: sqlite3.Row) -> dict[str, Any]:
        result = cls._summary(row)
        result["messages"] = cls._decoded_messages(row)
        return result
