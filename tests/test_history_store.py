from __future__ import annotations

from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "apps" / "internal-portal" / "backend"))

from app.history_store import HistoryStore  # noqa: E402


class HistoryStoreTests(unittest.TestCase):
    def test_history_is_persistent_and_owner_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(str(Path(directory) / "history.sqlite3"))
            record = store.upsert(
                "wecom:alice",
                "purchase",
                None,
                "rag-session-1",
                "GS-30W0989 报价",
                [{"role": "user", "content": "查询 GS-30W0989 报价"}],
            )

            reopened = HistoryStore(str(Path(directory) / "history.sqlite3"))
            self.assertEqual(reopened.list("wecom:alice", "purchase")[0]["id"], record["id"])
            self.assertEqual(reopened.get("wecom:alice", record["id"])["messages"][0]["content"], "查询 GS-30W0989 报价")
            self.assertEqual(reopened.list("wecom:bob", "purchase"), [])
            self.assertEqual(reopened.list("wecom:alice", "sales"), [])


if __name__ == "__main__":
    unittest.main()
