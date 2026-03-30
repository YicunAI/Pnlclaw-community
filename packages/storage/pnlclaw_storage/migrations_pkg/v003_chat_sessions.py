"""V003 — Chat session persistence.

Creates 2 tables:
  1. chat_sessions  — conversation sessions (per strategy or global)
  2. chat_messages   — individual messages within a session

Allows the frontend to persist, list, and switch conversation history.
"""

from __future__ import annotations

import aiosqlite

from pnlclaw_storage.migrations import Migration

_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id           TEXT PRIMARY KEY,
        strategy_id  TEXT,
        title        TEXT NOT NULL DEFAULT '',
        created_at   TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_strategy_id ON chat_sessions (strategy_id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at  ON chat_sessions (updated_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id           TEXT PRIMARY KEY,
        session_id   TEXT NOT NULL,
        role         TEXT NOT NULL,
        content      TEXT NOT NULL DEFAULT '',
        extra_json   TEXT NOT NULL DEFAULT '{}',
        created_at   TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id  ON chat_messages (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at  ON chat_messages (created_at)",
]


async def _apply(conn: aiosqlite.Connection) -> None:
    for stmt in _STATEMENTS:
        await conn.execute(stmt)


migration = Migration(
    id="v003_chat_sessions",
    version=3,
    description="Add chat_sessions and chat_messages for conversation persistence",
    apply=_apply,
)
