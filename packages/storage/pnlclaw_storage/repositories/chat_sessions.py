"""Repository for chat session and message persistence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pnlclaw_storage.sqlite import AsyncSQLiteManager


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix: str = "cs") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class ChatSessionRepository:
    """CRUD operations for chat sessions and messages."""

    def __init__(self, db: AsyncSQLiteManager) -> None:
        self._db = db

    # ---- Sessions ----

    async def create_session(
        self,
        strategy_id: str | None = None,
        title: str = "",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        sid = session_id or _new_id("cs")
        now = _now_iso()
        await self._db.execute(
            "INSERT INTO chat_sessions (id, strategy_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (sid, strategy_id, title, now, now),
        )
        return {"id": sid, "strategy_id": strategy_id, "title": title, "created_at": now, "updated_at": now}

    async def list_sessions(
        self,
        strategy_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if strategy_id:
            rows = await self._db.query(
                "SELECT s.*, "
                "  (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS message_count "
                "FROM chat_sessions s "
                "WHERE s.strategy_id = ? ORDER BY s.updated_at DESC LIMIT ? OFFSET ?",
                (strategy_id, limit, offset),
            )
        else:
            rows = await self._db.query(
                "SELECT s.*, "
                "  (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS message_count "
                "FROM chat_sessions s "
                "ORDER BY s.updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [dict(r) for r in rows]

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        rows = await self._db.query(
            "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
        )
        return dict(rows[0]) if rows else None

    async def update_session_title(self, session_id: str, title: str) -> None:
        await self._db.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now_iso(), session_id),
        )

    async def touch_session(self, session_id: str) -> None:
        await self._db.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            (_now_iso(), session_id),
        )

    async def delete_session(self, session_id: str) -> None:
        await self._db.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))

    # ---- Messages ----

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        extra: dict[str, Any] | None = None,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        mid = message_id or _new_id("cm")
        now = _now_iso()
        extra_json = json.dumps(extra or {}, ensure_ascii=False)
        await self._db.execute(
            "INSERT INTO chat_messages (id, session_id, role, content, extra_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (mid, session_id, role, content, extra_json, now),
        )
        await self.touch_session(session_id)
        return {"id": mid, "session_id": session_id, "role": role, "content": content, "extra": extra or {}, "created_at": now}

    async def get_messages(
        self, session_id: str, limit: int = 200, offset: int = 0,
    ) -> list[dict[str, Any]]:
        rows = await self._db.query(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?",
            (session_id, limit, offset),
        )
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["extra"] = json.loads(d.pop("extra_json", "{}"))
            except (json.JSONDecodeError, KeyError):
                d["extra"] = {}
            result.append(d)
        return result

    async def save_messages_bulk(
        self, session_id: str, messages: list[dict[str, Any]],
    ) -> None:
        """Upsert a batch of messages in a single transaction."""
        params = []
        now = _now_iso()
        for msg in messages:
            mid = msg.get("id") or _new_id("cm")
            role = msg.get("role", "user")
            content = msg.get("content", "")
            extra = msg.get("extra") or msg.get("reasoningSteps") or {}
            extra_json = json.dumps(extra, ensure_ascii=False) if isinstance(extra, (dict, list)) else "{}"
            params.append((mid, session_id, role, content, extra_json, now))
        if not params:
            return
        async with self._db.connection() as conn:
            await conn.execute(
                "DELETE FROM chat_messages WHERE session_id = ?", (session_id,)
            )
            await conn.executemany(
                "INSERT INTO chat_messages (id, session_id, role, content, extra_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                params,
            )
            await conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
