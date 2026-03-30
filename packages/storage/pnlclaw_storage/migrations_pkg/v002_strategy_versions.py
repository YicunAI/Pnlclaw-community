"""V002 — Strategy versions, deployments, and backtest version binding."""

from __future__ import annotations

import aiosqlite

from pnlclaw_storage.migrations import Migration

_STATEMENTS: list[str] = [
    "ALTER TABLE strategies ADD COLUMN version INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE strategies ADD COLUMN lifecycle_state TEXT NOT NULL DEFAULT 'draft'",
    "ALTER TABLE backtests ADD COLUMN strategy_version INTEGER NOT NULL DEFAULT 1",
    """
    CREATE TABLE IF NOT EXISTS strategy_versions (
        id                TEXT PRIMARY KEY,
        strategy_id       TEXT NOT NULL,
        version           INTEGER NOT NULL,
        config_json       TEXT NOT NULL DEFAULT '{}',
        note              TEXT NOT NULL DEFAULT '',
        created_at        TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (strategy_id) REFERENCES strategies (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_strategy_versions_strategy_id ON strategy_versions (strategy_id)",
    "CREATE INDEX IF NOT EXISTS idx_strategy_versions_version ON strategy_versions (strategy_id, version)",
    """
    CREATE TABLE IF NOT EXISTS strategy_deployments (
        id                TEXT PRIMARY KEY,
        strategy_id       TEXT NOT NULL,
        strategy_version  INTEGER NOT NULL DEFAULT 1,
        account_id        TEXT NOT NULL,
        mode              TEXT NOT NULL DEFAULT 'paper',
        status            TEXT NOT NULL DEFAULT 'running',
        created_at        TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (strategy_id) REFERENCES strategies (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_strategy_deployments_strategy_id ON strategy_deployments (strategy_id)",
]


async def _apply(conn: aiosqlite.Connection) -> None:
    for stmt in _STATEMENTS:
        try:
            await conn.execute(stmt)
        except aiosqlite.OperationalError as exc:
            message = str(exc).lower()
            if "duplicate column name" in message:
                continue
            raise


migration = Migration(
    id="v002_strategy_versions",
    version=2,
    description="Add strategy versions, deployments, and backtest version binding",
    apply=_apply,
)
