"""Async SQLite manager with WAL mode and automatic migrations.

Provides a thin async wrapper around aiosqlite with:
- Single connection + WAL mode (safe for concurrent reads)
- Context-managed connection access
- Automatic migration on first connect
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

from pnlclaw_storage.migrations import MigrationRunner
from pnlclaw_storage.migrations_pkg import ALL_MIGRATIONS

# Default database path: ~/.pnlclaw/data/pnlclaw.db
DEFAULT_DB_PATH = Path.home() / ".pnlclaw" / "data" / "pnlclaw.db"


class StorageError(Exception):
    """Base exception for storage operations."""


class ConnectionError(StorageError):
    """Failed to establish or maintain a database connection."""


class AsyncSQLiteManager:
    """Async SQLite manager with WAL mode and connection lifecycle.

    Uses a single persistent aiosqlite connection with WAL journal mode,
    which allows concurrent reads while a write is in progress.

    Args:
        db_path: Path to the SQLite database file. Use \":memory:\" for
            in-memory databases (useful for testing).
        migration_runner: Optional migration runner executed on first connect.
    """

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        migration_runner: MigrationRunner | None = None,
    ) -> None:
        self._db_path = str(db_path)
        self._migration_runner = migration_runner or MigrationRunner(ALL_MIGRATIONS)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Whether the manager currently holds an open connection."""
        return self._conn is not None

    async def connect(self) -> None:
        """Open the database connection and run pending migrations.

        Creates parent directories if the path is a file (not :memory:).
        Enables WAL journal mode and foreign keys.
        """
        async with self._lock:
            if self._conn is not None:
                return

            # Ensure parent directory exists for file-based databases
            if self._db_path != ":memory:":
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

            conn = await aiosqlite.connect(self._db_path)
            conn.row_factory = aiosqlite.Row

            # Enable WAL mode for concurrent read access
            await conn.execute("PRAGMA journal_mode=WAL")
            # Enable foreign key enforcement
            await conn.execute("PRAGMA foreign_keys=ON")

            self._conn = conn

            # Run pending migrations if a runner is configured
            if self._migration_runner is not None:
                await self._migration_runner.run_pending(conn)

    async def close(self) -> None:
        """Close the database connection."""
        async with self._lock:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None

    def _require_connection(self) -> aiosqlite.Connection:
        """Return the active connection or raise."""
        if self._conn is None:
            raise ConnectionError(
                "Database not connected. Call connect() first."
            )
        return self._conn

    async def execute(
        self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()
    ) -> list[aiosqlite.Row]:
        """Execute a SQL statement and return all result rows.

        Args:
            sql: SQL statement (may contain ``?`` or ``:name`` placeholders).
            params: Positional or named parameters for the statement.

        Returns:
            List of Row objects (dict-like access by column name).
        """
        conn = self._require_connection()
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        await conn.commit()
        return rows

    async def execute_many(
        self, sql: str, params_list: list[tuple[Any, ...]]
    ) -> None:
        """Execute a SQL statement against each parameter set.

        Args:
            sql: SQL statement with ``?`` placeholders.
            params_list: List of parameter tuples.
        """
        conn = self._require_connection()
        await conn.executemany(sql, params_list)
        await conn.commit()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Yield the underlying aiosqlite connection for advanced use.

        The connection is committed on successful exit and rolled back on
        exception. Callers should prefer ``execute`` / ``execute_many`` for
        simple operations.
        """
        conn = self._require_connection()
        try:
            yield conn
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise

    async def __aenter__(self) -> AsyncSQLiteManager:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
