"""V005 — Persist symbol and interval in backtests table."""

from __future__ import annotations

import aiosqlite

from pnlclaw_storage.migrations import Migration

_STATEMENTS: list[str] = [
    "ALTER TABLE backtests ADD COLUMN symbol TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE backtests ADD COLUMN interval TEXT NOT NULL DEFAULT '1h'",
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
    id="v005_backtest_symbol_interval",
    version=5,
    description="Add symbol and interval columns to backtests",
    apply=_apply,
)
