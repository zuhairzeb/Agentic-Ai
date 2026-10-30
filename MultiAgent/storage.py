"""SQLite schema and user-scoped settings and saved-memory storage."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from config import Config


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLiteStore:
    """Local storage for response settings and explicit saved memories."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or Config().database_path)
        self._lock = RLock()
        self.initialize()

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create app tables; leave any old chat tables and their data untouched."""
        with self._lock, self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                '''
                CREATE TABLE IF NOT EXISTS app_settings (
                    user_identifier TEXT PRIMARY KEY,
                    values_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS saved_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_identifier TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memories_user ON saved_memories(user_identifier, id);
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_identifier TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    temporary INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
                    ON conversations(user_identifier, archived, updated_at);
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    message_key TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(conversation_id, message_key)
                );
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_search
                    ON conversation_messages(conversation_id, role);
                CREATE TABLE IF NOT EXISTS library_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_identifier TEXT NOT NULL,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_identifier, name)
                );
                CREATE INDEX IF NOT EXISTS idx_library_user ON library_documents(user_identifier, id);
                CREATE TABLE IF NOT EXISTS platform_items (
                    user_identifier TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    values_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_identifier,item_type,item_id)
                );
                CREATE INDEX IF NOT EXISTS idx_platform_items_user_type
                    ON platform_items(user_identifier,item_type,updated_at);
                '''
            )
            # Preserve settings and saved memories from the former local login profile.
            conn.execute(
                "INSERT INTO app_settings(user_identifier, values_json, updated_at) "
                "SELECT 'local', values_json, updated_at FROM app_settings "
                "WHERE user_identifier='local@example.com' "
                "ON CONFLICT(user_identifier) DO NOTHING"
            )
            conn.execute("DELETE FROM app_settings WHERE user_identifier='local@example.com'")
            conn.execute(
                "UPDATE saved_memories SET user_identifier='local' "
                "WHERE user_identifier='local@example.com'"
            )
            conn.execute("PRAGMA user_version=3")

    def save_conversation_message(
        self, conversation_id: str, user_identifier: str, role: str,
        content: str, message_key: str, temporary: bool = False,
    ) -> bool:
        if role not in {"user", "assistant"}:
            raise ValueError("Conversation message role must be user or assistant.")
        if temporary:
            return False
        now = utc_now()
        with self._lock, self.connect() as conn:
            exists = conn.execute(
                "SELECT temporary FROM conversations WHERE id=? AND user_identifier=?",
                (conversation_id, user_identifier),
            ).fetchone()
            if exists and exists["temporary"]:
                return False
            if not exists:
                title = " ".join(content.split())[:80] or "New conversation"
                conn.execute(
                    "INSERT INTO conversations(id,user_identifier,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (conversation_id, user_identifier, title, now, now),
                )
            result = conn.execute(
                "INSERT OR IGNORE INTO conversation_messages(conversation_id,message_key,role,content,created_at) "
                "SELECT ?,?,?,?,? WHERE EXISTS(SELECT 1 FROM conversations WHERE id=? AND user_identifier=?)",
                (conversation_id, message_key, role, content, now, conversation_id, user_identifier),
            )
            conn.execute("UPDATE conversations SET updated_at=? WHERE id=? AND user_identifier=?", (now, conversation_id, user_identifier))
            if role == "user":
                title = " ".join(content.split())[:80] or "New conversation"
                conn.execute(
                    "UPDATE conversations SET title=? WHERE id=? AND user_identifier=? AND title IN ('New conversation','New chat')",
                    (title, conversation_id, user_identifier),
                )
            return result.rowcount == 1

    def create_conversation(self, user_identifier: str, conversation_id: str | None = None) -> dict[str, Any]:
        """Create a saved conversation and return its new record."""
        conversation_id = conversation_id or __import__("uuid").uuid4().hex
        now = utc_now()
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT INTO conversations(id,user_identifier,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                (conversation_id, user_identifier, "New chat", now, now),
            )
        return self.get_conversation(conversation_id, user_identifier) or {}

    def get_conversation_messages(self, conversation_id: str, user_identifier: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT m.role,m.content,m.created_at,m.message_key FROM conversation_messages m "
                "JOIN conversations c ON c.id=m.conversation_id "
                "WHERE c.id=? AND c.user_identifier=? ORDER BY m.id",
                (conversation_id, user_identifier),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_conversation(self, conversation_id: str, user_identifier: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id,title,created_at,updated_at,pinned,archived,temporary FROM conversations WHERE id=? AND user_identifier=?",
                (conversation_id, user_identifier),
            ).fetchone()
        return dict(row) if row else None

    def set_conversation_temporary(self, conversation_id: str, user_identifier: str, temporary: bool) -> None:
        with self._lock, self.connect() as conn:
            conn.execute(
                "UPDATE conversations SET temporary=?,updated_at=? WHERE id=? AND user_identifier=?",
                (int(temporary), utc_now(), conversation_id, user_identifier),
            )

    def delete_last_assistant_message(self, conversation_id: str, user_identifier: str) -> bool:
        with self._lock, self.connect() as conn:
            row = conn.execute(
                "SELECT m.id FROM conversation_messages m JOIN conversations c ON c.id=m.conversation_id "
                "WHERE c.id=? AND c.user_identifier=? AND m.role='assistant' ORDER BY m.id DESC LIMIT 1",
                (conversation_id, user_identifier),
            ).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM conversation_messages WHERE id=?", (row["id"],))
            conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (utc_now(), conversation_id))
            return True

    def list_conversations(self, user_identifier: str, archived: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id,title,created_at,updated_at,pinned,archived,temporary FROM conversations "
                "WHERE user_identifier=? AND archived=? AND temporary=0 "
                "ORDER BY pinned DESC,updated_at DESC LIMIT ?",
                (user_identifier, int(archived), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_conversations(self, user_identifier: str, query: str, limit: int = 50) -> list[dict[str, Any]]:
        needle = f"%{query.strip()}%"
        if not query.strip():
            return []
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT c.id,c.title,c.updated_at,c.pinned,c.archived FROM conversations c "
                "LEFT JOIN conversation_messages m ON m.conversation_id=c.id "
                "WHERE c.user_identifier=? AND c.temporary=0 AND (c.title LIKE ? OR m.content LIKE ?) "
                "ORDER BY c.pinned DESC,c.updated_at DESC LIMIT ?",
                (user_identifier, needle, needle, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_conversation_flag(self, conversation_id: str, user_identifier: str, flag: str, enabled: bool) -> bool:
        if flag not in {"pinned", "archived"}:
            raise ValueError("Unsupported conversation flag.")
        with self._lock, self.connect() as conn:
            result = conn.execute(
                f"UPDATE conversations SET {flag}=?,updated_at=? WHERE id=? AND user_identifier=?",
                (int(enabled), utc_now(), conversation_id, user_identifier),
            )
        return result.rowcount == 1

    def rename_conversation(self, conversation_id: str, user_identifier: str, title: str) -> bool:
        title = " ".join(title.split())[:80]
        if not title:
            return False
        with self._lock, self.connect() as conn:
            result = conn.execute(
                "UPDATE conversations SET title=?,updated_at=? WHERE id=? AND user_identifier=?",
                (title, utc_now(), conversation_id, user_identifier),
            )
        return result.rowcount == 1

    def delete_conversation(self, conversation_id: str, user_identifier: str) -> bool:
        with self._lock, self.connect() as conn:
            conn.execute(
                "DELETE FROM conversation_messages WHERE conversation_id=? AND conversation_id IN "
                "(SELECT id FROM conversations WHERE user_identifier=?)",
                (conversation_id, user_identifier),
            )
            result = conn.execute("DELETE FROM conversations WHERE id=? AND user_identifier=?", (conversation_id, user_identifier))
        return result.rowcount == 1

    def delete_all_conversations(self, user_identifier: str) -> int:
        """Delete all saved conversations belonging to one user."""
        with self._lock, self.connect() as conn:
            conn.execute(
                "DELETE FROM conversation_messages WHERE conversation_id IN "
                "(SELECT id FROM conversations WHERE user_identifier=?)",
                (user_identifier,),
            )
            result = conn.execute("DELETE FROM conversations WHERE user_identifier=?", (user_identifier,))
            return result.rowcount

    def save_library_document(self, user_identifier: str, name: str, content: str) -> int:
        now = utc_now()
        safe_name = Path(name).name[:255]
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT INTO library_documents(user_identifier,name,content,created_at,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(user_identifier,name) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at",
                (user_identifier, safe_name, content[:100000], now, now),
            )
            row = conn.execute("SELECT id FROM library_documents WHERE user_identifier=? AND name=?", (user_identifier, safe_name)).fetchone()
        return int(row["id"])

    def list_library_documents(self, user_identifier: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT id,name,created_at,updated_at FROM library_documents WHERE user_identifier=? ORDER BY updated_at DESC", (user_identifier,)).fetchall()
        return [dict(row) for row in rows]

    def search_library_documents(self, user_identifier: str, query: str, limit: int = 3) -> list[dict[str, Any]]:
        terms = list(dict.fromkeys(re.findall(r"[\w'-]{3,}", query.lower())))[:8]
        if not terms:
            return []
        where = " OR ".join("lower(content) LIKE ?" for _ in terms)
        params = [user_identifier, *(f"%{term}%" for term in terms)]
        with self.connect() as conn:
            rows = conn.execute(f"SELECT id,name,content FROM library_documents WHERE user_identifier=? AND ({where}) LIMIT ?", (*params, limit)).fetchall()
        return [dict(row) for row in rows]

    def delete_library_document(self, user_identifier: str, document_id: int) -> bool:
        with self._lock, self.connect() as conn:
            result = conn.execute("DELETE FROM library_documents WHERE user_identifier=? AND id=?", (user_identifier, document_id))
        return result.rowcount == 1

    def clear_conversation_messages(self, conversation_id: str, user_identifier: str) -> int:
        with self._lock, self.connect() as conn:
            result = conn.execute(
                "DELETE FROM conversation_messages WHERE conversation_id=? AND conversation_id IN "
                "(SELECT id FROM conversations WHERE user_identifier=?)",
                (conversation_id, user_identifier),
            )
            conn.execute("UPDATE conversations SET title='New conversation',updated_at=? WHERE id=? AND user_identifier=?", (utc_now(), conversation_id, user_identifier))
        return result.rowcount

    def get_settings(self, user_identifier: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT values_json FROM app_settings WHERE user_identifier=?",
                (user_identifier,),
            ).fetchone()
        return json.loads(row["values_json"]) if row else {}

    def save_settings(self, user_identifier: str, values: dict[str, Any]) -> None:
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT INTO app_settings(user_identifier, values_json, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(user_identifier) DO UPDATE SET values_json=excluded.values_json, updated_at=excluded.updated_at",
                (user_identifier, json.dumps(values), utc_now()),
            )

    def save_platform_item(self, user_identifier: str, item_type: str, item_id: str, values: dict[str, Any], enabled: bool = True) -> None:
        now = utc_now()
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT INTO platform_items(user_identifier,item_type,item_id,values_json,enabled,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_identifier,item_type,item_id) DO UPDATE SET "
                "values_json=excluded.values_json,enabled=excluded.enabled,updated_at=excluded.updated_at",
                (user_identifier, item_type, item_id, json.dumps(values, ensure_ascii=False), int(enabled), now, now),
            )

    def list_platform_items(self, user_identifier: str, item_type: str, include_disabled: bool = True) -> list[dict[str, Any]]:
        query = "SELECT item_id,values_json,enabled,created_at,updated_at FROM platform_items WHERE user_identifier=? AND item_type=?"
        params: tuple[Any, ...] = (user_identifier, item_type)
        if not include_disabled:
            query += " AND enabled=1"
        query += " ORDER BY updated_at DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [{"id": row["item_id"], **json.loads(row["values_json"]), "enabled": bool(row["enabled"]), "created_at": row["created_at"], "updated_at": row["updated_at"]} for row in rows]

    def get_platform_item(self, user_identifier: str, item_type: str, item_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT item_id,values_json,enabled,created_at,updated_at FROM platform_items WHERE user_identifier=? AND item_type=? AND item_id=?",
                (user_identifier, item_type, item_id),
            ).fetchone()
        return {"id": row["item_id"], **json.loads(row["values_json"]), "enabled": bool(row["enabled"]), "created_at": row["created_at"], "updated_at": row["updated_at"]} if row else None

    def set_platform_item_enabled(self, user_identifier: str, item_type: str, item_id: str, enabled: bool) -> bool:
        with self._lock, self.connect() as conn:
            result = conn.execute(
                "UPDATE platform_items SET enabled=?,updated_at=? WHERE user_identifier=? AND item_type=? AND item_id=?",
                (int(enabled), utc_now(), user_identifier, item_type, item_id),
            )
        return result.rowcount == 1

    def delete_platform_item(self, user_identifier: str, item_type: str, item_id: str) -> bool:
        with self._lock, self.connect() as conn:
            result = conn.execute(
                "DELETE FROM platform_items WHERE user_identifier=? AND item_type=? AND item_id=?",
                (user_identifier, item_type, item_id),
            )
        return result.rowcount == 1

    def add_memory(self, user_identifier: str, content: str) -> int:
        now = utc_now()
        with self._lock, self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM saved_memories WHERE user_identifier=? AND lower(trim(content))=lower(trim(?)) ORDER BY id LIMIT 1",
                (user_identifier, content),
            ).fetchone()
            if existing:
                return int(existing["id"])
            cursor = conn.execute(
                "INSERT INTO saved_memories(user_identifier, content, created_at, updated_at) VALUES(?,?,?,?)",
                (user_identifier, content, now, now),
            )
            return int(cursor.lastrowid)

    def list_memories(self, user_identifier: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, content, created_at, updated_at FROM saved_memories WHERE user_identifier=? ORDER BY id",
                (user_identifier,),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_memories(self, user_identifier: str, query: str, limit: int = 4) -> list[dict[str, Any]]:
        """Return only explicitly saved memories with lexical overlap to the current request."""
        import re
        stop_words = {"about", "after", "also", "and", "are", "can", "could", "for", "from", "have", "help", "how", "into", "please", "that", "the", "this", "what", "when", "where", "with", "would", "your"}
        terms = {term for term in re.findall(r"[a-z0-9]{3,}", query.lower()) if term not in stop_words}
        if not terms:
            return []
        memories = self.list_memories(user_identifier)
        scored = []
        for item in memories:
            content_terms = set(re.findall(r"[a-z0-9]{3,}", item["content"].lower()))
            score = len(terms & content_terms)
            if score:
                scored.append((score, item))
        scored.sort(key=lambda entry: (-entry[0], entry[1]["id"]))
        return [item for _, item in scored[:limit]]

    def edit_memory(self, user_identifier: str, memory_id: int, content: str) -> bool:
        with self._lock, self.connect() as conn:
            result = conn.execute(
                "UPDATE saved_memories SET content=?, updated_at=? WHERE id=? AND user_identifier=?",
                (content, utc_now(), memory_id, user_identifier),
            )
            return result.rowcount == 1

    def delete_memory(self, user_identifier: str, memory_id: int) -> bool:
        with self._lock, self.connect() as conn:
            result = conn.execute(
                "DELETE FROM saved_memories WHERE id=? AND user_identifier=?",
                (memory_id, user_identifier),
            )
            return result.rowcount == 1

    def clear_memories(self, user_identifier: str) -> int:
        with self._lock, self.connect() as conn:
            result = conn.execute("DELETE FROM saved_memories WHERE user_identifier=?", (user_identifier,))
            return result.rowcount


store = SQLiteStore()
