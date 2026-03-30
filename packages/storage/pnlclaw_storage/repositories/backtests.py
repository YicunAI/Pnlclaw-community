"""Backtest result CRUD repository.

Persists ``BacktestResult`` models to the ``backtests`` table,
serializing ``metrics`` and ``equity_curve`` as JSON columns.
Additional analysis fields not yet present in the schema are preserved
in ``metrics_json``-adjacent reconstruction fallbacks where possible.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast

import aiosqlite

from pnlclaw_storage.sqlite import AsyncSQLiteManager
from pnlclaw_types.strategy import BacktestMetrics, BacktestResult


def _timestamp_ms_to_storage(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()


def _storage_to_timestamp_ms(value: str) -> int:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return int(dt.timestamp() * 1000)


class BacktestRepository:
    """CRUD operations for backtest results.

    Args:
        db: An initialized ``AsyncSQLiteManager`` instance.
    """

    def __init__(self, db: AsyncSQLiteManager) -> None:
        self._db = db

    async def save(self, result: BacktestResult) -> str:
        """Insert a backtest result.

        Args:
            result: The backtest result to persist.

        Returns:
            The backtest ID.
        """
        created_at = _timestamp_ms_to_storage(result.created_at)
        metrics_json = result.metrics.model_dump_json()
        equity_json = json.dumps(result.equity_curve)
        buy_hold_json = json.dumps(result.buy_hold_curve) if result.buy_hold_curve else "[]"
        drawdown_json = json.dumps(result.drawdown_curve) if result.drawdown_curve else "[]"
        trades_json = json.dumps(result.trades) if result.trades else "[]"

        await self._db.execute(
            """
            INSERT INTO backtests
                (id, strategy_id, start_date, end_date,
                 metrics_json, equity_curve_json, trades_count, created_at, strategy_version,
                 buy_hold_curve_json, drawdown_curve_json, trades_json,
                 symbol, interval)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                metrics_json = excluded.metrics_json,
                equity_curve_json = excluded.equity_curve_json,
                trades_count = excluded.trades_count,
                strategy_version = excluded.strategy_version,
                buy_hold_curve_json = excluded.buy_hold_curve_json,
                drawdown_curve_json = excluded.drawdown_curve_json,
                trades_json = excluded.trades_json,
                symbol = excluded.symbol,
                interval = excluded.interval
            """,
            (
                result.id,
                result.strategy_id,
                result.start_date.isoformat(),
                result.end_date.isoformat(),
                metrics_json,
                equity_json,
                result.trades_count,
                created_at,
                int(getattr(result, "strategy_version", 1)),
                buy_hold_json,
                drawdown_json,
                trades_json,
                result.symbol,
                result.interval,
            ),
        )
        return result.id

    def _row_to_result(self, row: aiosqlite.Row) -> BacktestResult:
        """Convert a database row to a BacktestResult."""
        keys = row.keys()
        equity_curve = json.loads(cast(str, row["equity_curve_json"]))

        buy_hold_curve: list[float] = []
        if "buy_hold_curve_json" in keys and row["buy_hold_curve_json"]:
            try:
                buy_hold_curve = json.loads(cast(str, row["buy_hold_curve_json"]))
            except (json.JSONDecodeError, TypeError):
                pass

        drawdown_curve: list[float] = []
        if "drawdown_curve_json" in keys and row["drawdown_curve_json"]:
            try:
                drawdown_curve = json.loads(cast(str, row["drawdown_curve_json"]))
            except (json.JSONDecodeError, TypeError):
                pass

        trades: list[dict] = []
        if "trades_json" in keys and row["trades_json"]:
            try:
                trades = json.loads(cast(str, row["trades_json"]))
            except (json.JSONDecodeError, TypeError):
                pass

        if not drawdown_curve and len(equity_curve) >= 2:
            import numpy as np
            eq = np.asarray(equity_curve, dtype=np.float64)
            peak = np.maximum.accumulate(eq)
            dd = ((eq - peak) / peak).tolist()
            drawdown_curve = [round(v, 8) for v in dd]

        if not buy_hold_curve and len(equity_curve) >= 2:
            start_val = equity_curve[0]
            end_val = equity_curve[-1]
            ratio = end_val / start_val if start_val else 1.0
            buy_hold_curve = [
                round(start_val * (1 + (ratio - 1) * (i / (len(equity_curve) - 1))), 2)
                for i in range(len(equity_curve))
            ]

        symbol = cast(str, row["symbol"]) if "symbol" in keys and row["symbol"] is not None else ""
        interval = cast(str, row["interval"]) if "interval" in keys and row["interval"] is not None else "1h"

        return BacktestResult(
            id=cast(str, row["id"]),
            strategy_id=cast(str, row["strategy_id"]),
            strategy_version=cast(int, row["strategy_version"]) if "strategy_version" in keys else 1,
            symbol=symbol,
            interval=interval,
            start_date=datetime.fromisoformat(cast(str, row["start_date"])),
            end_date=datetime.fromisoformat(cast(str, row["end_date"])),
            metrics=BacktestMetrics.model_validate_json(cast(str, row["metrics_json"])),
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            buy_hold_curve=buy_hold_curve,
            trades=trades,
            trades_count=cast(int, row["trades_count"]),
            created_at=_storage_to_timestamp_ms(cast(str, row["created_at"])),
        )

    async def get(self, backtest_id: str) -> BacktestResult | None:
        """Retrieve a backtest result by ID.

        Args:
            backtest_id: The backtest identifier.

        Returns:
            The backtest result, or ``None`` if not found.
        """
        rows = await self._db.query(
            """
            SELECT id, strategy_id, strategy_version, start_date, end_date,
                   metrics_json, equity_curve_json, trades_count, created_at,
                   buy_hold_curve_json, drawdown_curve_json, trades_json,
                   symbol, interval
            FROM backtests WHERE id = ?
            """,
            (backtest_id,),
        )
        if not rows:
            return None
        return self._row_to_result(rows[0])

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[BacktestResult]:
        """List all backtest results, newest first."""
        rows = await self._db.query(
            """
            SELECT id, strategy_id, strategy_version, start_date, end_date,
                   metrics_json, equity_curve_json, trades_count, created_at,
                   buy_hold_curve_json, drawdown_curve_json, trades_json,
                   symbol, interval
            FROM backtests
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [self._row_to_result(r) for r in rows]

    async def delete(self, backtest_id: str) -> bool:
        """Delete a backtest result by ID.

        Returns:
            True if the row was found and deleted, False otherwise.
        """
        await self._db.execute(
            "DELETE FROM backtests WHERE id = ?",
            (backtest_id,),
        )
        # aiosqlite doesn't surface rowcount easily, so we check existence first
        rows = await self._db.query(
            "SELECT id FROM backtests WHERE id = ?",
            (backtest_id,),
        )
        return len(rows) == 0

    async def list_by_strategy(self, strategy_id: str, limit: int = 20) -> list[BacktestResult]:
        """List backtest results for a strategy, newest first.

        Args:
            strategy_id: The strategy to filter by.
            limit: Maximum number of results.

        Returns:
            List of backtest results.
        """
        rows = await self._db.query(
            """
            SELECT id, strategy_id, strategy_version, start_date, end_date,
                   metrics_json, equity_curve_json, trades_count, created_at,
                   buy_hold_curve_json, drawdown_curve_json, trades_json,
                   symbol, interval
            FROM backtests
            WHERE strategy_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (strategy_id, limit),
        )
        return [self._row_to_result(r) for r in rows]
