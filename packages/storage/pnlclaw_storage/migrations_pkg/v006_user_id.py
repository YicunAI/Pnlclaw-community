"""V006 — Add user_id column to all business tables for multi-user isolation.

Adds ``user_id TEXT NOT NULL DEFAULT 'local'`` to:
  - strategies
  - backtests
  - paper_accounts
  - chat_sessions
  - audit_logs

Paper orders, positions, and equity history are isolated indirectly
through their parent account_id (which now belongs to a specific user).

Existing rows get user_id='local' (the Community single-user identity).
"""

from __future__ import annotations

import aiosqlite

from pnlclaw_storage.migrations import Migration

_ALTER_STATEMENTS: list[str] = [
    "ALTER TABLE strategies ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'",
    "ALTER TABLE backtests ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'",
    "ALTER TABLE paper_accounts ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'",
    "ALTER TABLE chat_sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'",
    "ALTER TABLE audit_logs ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'",
]

_INDEX_STATEMENTS: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_strategies_user_id ON strategies (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_strategies_user_name ON strategies (user_id, name)",
    "CREATE INDEX IF NOT EXISTS idx_backtests_user_id ON backtests (user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_paper_accounts_user_id ON paper_accounts (user_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions (user_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs (user_id)",
]


async def _apply(conn: aiosqlite.Connection) -> None:
    for stmt in _ALTER_STATEMENTS:
        try:
            await conn.execute(stmt)
        except Exception:
            pass
    for stmt in _INDEX_STATEMENTS:
        await conn.execute(stmt)


migration = Migration(
    id="v006_user_id",
    version=6,
    description="Add user_id column to strategies, backtests, paper_accounts, chat_sessions, audit_logs",
    apply=_apply,
)
