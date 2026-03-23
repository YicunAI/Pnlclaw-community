"""Backtest result CRUD repository.

Persists ``BacktestResult`` models to the ``backtests`` table,
serializing ``metrics`` and ``equity_curve`` as JSON columns.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pnlclaw_types.strategy import BacktestMetrics, BacktestResult

from pnlclaw_storage.sqlite import AsyncSQLiteManager


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
        now = datetime.now(timezone.utc).isoformat()
        metrics_json = result.metrics.model_dump_json()
        equity_json = json.dumps(result.equity_curve)

        await self._db.execute(
            """
            INSERT INTO backtests
                (id, strategy_id, start_date, end_date,
                 metrics_json, equity_curve_json, trades_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                metrics_json = excluded.metrics_json,
                equity_curve_json = excluded.equity_curve_json,
                trades_count = excluded.trades_count
            """,
            (
                result.id,
                result.strategy_id,
                result.start_date.isoformat(),
                result.end_date.isoformat(),
                metrics_json,
                equity_json,
                result.trades_count,
                now,
            ),
        )
        return result.id

    def _row_to_result(self, row: dict) -> BacktestResult:
        """Convert a database row to a BacktestResult."""
        return BacktestResult(
            id=row["id"],
            strategy_id=row["strategy_id"],
            start_date=datetime.fromisoformat(row["start_date"]),
            end_date=datetime.fromisoformat(row["end_date"]),
            metrics=BacktestMetrics.model_validate_json(row["metrics_json"]),
            equity_curve=json.loads(row["equity_curve_json"]),
            trades_count=row["trades_count"],
            created_at=int(
                datetime.fromisoformat(row["created_at"])
                .replace(tzinfo=timezone.utc)
                .timestamp()
                * 1000
            ),
        )

    async def get(self, backtest_id: str) -> BacktestResult | None:
        """Retrieve a backtest result by ID.

        Args:
            backtest_id: The backtest identifier.

        Returns:
            The backtest result, or ``None`` if not found.
        """
        rows = await self._db.execute(
            """
            SELECT id, strategy_id, start_date, end_date,
                   metrics_json, equity_curve_json, trades_count, created_at
            FROM backtests WHERE id = ?
            """,
            (backtest_id,),
        )
        if not rows:
            return None
        return self._row_to_result(rows[0])

    async def list_by_strategy(
        self, strategy_id: str, limit: int = 20
    ) -> list[BacktestResult]:
        """List backtest results for a strategy, newest first.

        Args:
            strategy_id: The strategy to filter by.
            limit: Maximum number of results.

        Returns:
            List of backtest results.
        """
        rows = await self._db.execute(
            """
            SELECT id, strategy_id, start_date, end_date,
                   metrics_json, equity_curve_json, trades_count, created_at
            FROM backtests
            WHERE strategy_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (strategy_id, limit),
        )
        return [self._row_to_result(r) for r in rows]
