"""Strategy CRUD repository.

Persists ``StrategyConfig`` models to the ``strategies`` table,
storing the full config as JSON in the ``config_json`` column.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pnlclaw_storage.sqlite import AsyncSQLiteManager
from pnlclaw_types.strategy import StrategyConfig


class StrategyRepository:
    """CRUD operations for strategies.

    Args:
        db: An initialized ``AsyncSQLiteManager`` instance.
    """

    def __init__(self, db: AsyncSQLiteManager) -> None:
        self._db = db

    async def save(self, strategy: StrategyConfig, *, user_id: str = "local") -> str:
        """Insert or update a strategy.

        Args:
            strategy: The strategy configuration to persist.
            user_id: Owner user ID (defaults to ``'local'`` for Community).

        Returns:
            The strategy ID.
        """
        now = datetime.now(UTC).isoformat()
        config_json = strategy.model_dump_json()

        await self._db.execute(
            """
            INSERT INTO strategies (id, name, type, config_json, created_at, updated_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                config_json = excluded.config_json,
                updated_at = excluded.updated_at
            """,
            (strategy.id, strategy.name, strategy.type.value, config_json, now, now, user_id),
        )
        return strategy.id

    async def get(self, strategy_id: str, *, user_id: str | None = None) -> StrategyConfig | None:
        """Retrieve a strategy by ID.

        Args:
            strategy_id: The strategy identifier.
            user_id: If provided, enforce ownership check.

        Returns:
            The strategy config, or ``None`` if not found.
        """
        if user_id is not None:
            rows = await self._db.query(
                "SELECT config_json FROM strategies WHERE id = ? AND user_id = ?",
                (strategy_id, user_id),
            )
        else:
            rows = await self._db.query(
                "SELECT config_json FROM strategies WHERE id = ?",
                (strategy_id,),
            )
        if not rows:
            return None
        return StrategyConfig.model_validate_json(rows[0]["config_json"])

    async def list(
        self,
        limit: int = 50,
        offset: int = 0,
        *,
        user_id: str | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
        strategy_type: str | None = None,
    ) -> list[StrategyConfig]:
        """List strategies ordered by last update, with minimal filtering.

        Args:
            user_id: If provided, filter to this user's strategies only.
        """
        if user_id is not None:
            rows = await self._db.query(
                "SELECT config_json FROM strategies WHERE user_id = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            )
        else:
            rows = await self._db.query(
                "SELECT config_json FROM strategies ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        strategies = [StrategyConfig.model_validate_json(r["config_json"]) for r in rows]

        if strategy_type is not None:
            strategies = [s for s in strategies if s.type.value == strategy_type]
        if source is not None:
            strategies = [s for s in strategies if s.source == source]
        if tags:
            tag_set = {t.strip().lower() for t in tags if t.strip()}
            strategies = [
                s for s in strategies
                if tag_set & {tag.lower() for tag in s.tags}
            ]
        return strategies

    async def delete(self, strategy_id: str, *, user_id: str | None = None) -> bool:
        """Delete a strategy by ID, optionally scoped by owner.

        Returns:
            ``True`` if a row was deleted, ``False`` if not found.
        """
        if user_id is not None:
            rows = await self._db.execute(
                "DELETE FROM strategies WHERE id = ? AND user_id = ? RETURNING id",
                (strategy_id, user_id),
            )
        else:
            rows = await self._db.execute(
                "DELETE FROM strategies WHERE id = ? RETURNING id",
                (strategy_id,),
            )
        return len(rows) > 0
