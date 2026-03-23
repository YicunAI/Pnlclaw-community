"""Declarative database migration framework.

Migrations are registered as ``Migration`` objects with a sequential version
number. ``MigrationRunner`` tracks which migrations have been applied via a
``_migrations`` table and executes pending ones in version order.

Design notes:
- Idempotent: already-applied migrations are never re-executed.
- Forward-compatible: v0.2 can add ``ALTER TABLE ADD COLUMN tenant_id``
  without rebuilding existing tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

import aiosqlite


class MigrationApplyFn(Protocol):
    """Callable signature for a migration's apply function."""

    def __call__(self, conn: aiosqlite.Connection) -> Awaitable[None]: ...


@dataclass(frozen=True, slots=True)
class Migration:
    """A single database migration.

    Attributes:
        id: Short stable identifier (e.g. ``v001_initial``).
        version: Numeric version for ordering (e.g. ``1``).
        description: Human-readable description of what this migration does.
        apply: Async callable that receives an aiosqlite connection and
            executes the migration DDL/DML.
    """

    id: str
    version: int
    description: str
    apply: Callable[[aiosqlite.Connection], Awaitable[None]]


class MigrationRunner:
    """Executes pending migrations in version order.

    Maintains a ``_migrations`` table to track which migrations have already
    been applied.  Calling ``run_pending`` is idempotent — previously applied
    migrations are skipped.

    Args:
        migrations: Ordered list of ``Migration`` objects to manage.
    """

    def __init__(self, migrations: list[Migration] | None = None) -> None:
        self._migrations: list[Migration] = sorted(
            migrations or [], key=lambda m: m.version
        )

    def register(self, migration: Migration) -> None:
        """Register an additional migration and re-sort."""
        self._migrations.append(migration)
        self._migrations.sort(key=lambda m: m.version)

    async def _ensure_table(self, conn: aiosqlite.Connection) -> None:
        """Create the ``_migrations`` tracking table if it does not exist."""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                id          TEXT PRIMARY KEY,
                version     INTEGER NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await conn.commit()

    async def _applied_ids(self, conn: aiosqlite.Connection) -> set[str]:
        """Return the set of migration IDs that have already been applied."""
        cursor = await conn.execute("SELECT id FROM _migrations")
        rows = await cursor.fetchall()
        return {row[0] for row in rows}

    async def run_pending(self, conn: aiosqlite.Connection) -> list[str]:
        """Execute all migrations that have not yet been applied.

        Args:
            conn: An open aiosqlite connection.

        Returns:
            List of descriptions for newly applied migrations.
        """
        await self._ensure_table(conn)
        applied = await self._applied_ids(conn)

        executed: list[str] = []
        for migration in self._migrations:
            if migration.id in applied:
                continue

            await migration.apply(conn)

            await conn.execute(
                "INSERT INTO _migrations (id, version, description) VALUES (?, ?, ?)",
                (migration.id, migration.version, migration.description),
            )
            await conn.commit()
            executed.append(migration.description)

        return executed
