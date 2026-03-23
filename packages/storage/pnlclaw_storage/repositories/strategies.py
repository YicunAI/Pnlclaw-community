"""Strategy CRUD repository.

Persists ``StrategyConfig`` models to the ``strategies`` table,
storing the full config as JSON in the ``config_json`` column.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pnlclaw_types.strategy import StrategyConfig

from pnlclaw_storage.sqlite import AsyncSQLiteManager


class StrategyRepository:
    """CRUD operations for strategies.

    Args:
        db: An initialized ``AsyncSQLiteManager`` instance.
    """

    def __init__(self, db: AsyncSQLiteManager) -> None:
        self._db = db

    async def save(self, strategy: StrategyConfig) -> str:
        """Insert or update a strategy.

        Args:
            strategy: The strategy configuration to persist.

        Returns:
            The strategy ID.
        """
        now = datetime.now(timezone.utc).isoformat()
        config_json = strategy.model_dump_json()

        await self._db.execute(
            """
            INSERT INTO strategies (id, name, type, config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                config_json = excluded.config_json,
                updated_at = excluded.updated_at
            """,
            (strategy.id, strategy.name, strategy.type.value, config_json, now, now),
        )
        return strategy.id

    async def get(self, strategy_id: str) -> StrategyConfig | None:
        """Retrieve a strategy by ID.

        Args:
            strategy_id: The strategy identifier.

        Returns:
            The strategy config, or ``None`` if not found.
        """
        rows = await self._db.execute(
            "SELECT config_json FROM strategies WHERE id = ?",
            (strategy_id,),
        )
        if not rows:
            return None
        return StrategyConfig.model_validate_json(rows[0]["config_json"])

    async def list(
        self, limit: int = 50, offset: int = 0
    ) -> list[StrategyConfig]:
        """List strategies ordered by creation date (newest first).

        Args:
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of strategy configs.
        """
        rows = await self._db.execute(
            "SELECT config_json FROM strategies ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [StrategyConfig.model_validate_json(r["config_json"]) for r in rows]

    async def delete(self, strategy_id: str) -> bool:
        """Delete a strategy by ID.

        Args:
            strategy_id: The strategy identifier.

        Returns:
            ``True`` if a row was deleted, ``False`` if not found.
        """
        rows = await self._db.execute(
            "DELETE FROM strategies WHERE id = ? RETURNING id",
            (strategy_id,),
        )
        return len(rows) > 0
