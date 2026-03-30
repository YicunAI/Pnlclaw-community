"""V004 — Persist buy_hold_curve, drawdown_curve, and trades in backtests table."""

from __future__ import annotations

import aiosqlite

from pnlclaw_storage.migrations import Migration

_STATEMENTS: list[str] = [
    "ALTER TABLE backtests ADD COLUMN buy_hold_curve_json TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE backtests ADD COLUMN drawdown_curve_json TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE backtests ADD COLUMN trades_json TEXT NOT NULL DEFAULT '[]'",
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
    id="v004_backtest_curves",
    version=4,
    description="Add buy_hold_curve, drawdown_curve, and trades columns to backtests",
    apply=_apply,
)
