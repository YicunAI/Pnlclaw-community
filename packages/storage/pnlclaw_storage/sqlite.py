"""Async SQLite manager with WAL mode and automatic migrations.

Provides a thin async wrapper around aiosqlite with:
- Single connection + WAL mode (safe for concurrent reads)
- Context-managed connection access
- Automatic migration on first connect
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

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
    """Async SQLite manager with WAL mode and read/write connection separation.

    Maintains two connections to properly leverage WAL mode:
    - A **write** connection (serialized via ``_write_lock``) for INSERT/UPDATE/DELETE
    - A **read** connection (serialized via ``_read_lock``) for SELECT queries

    Because WAL allows concurrent readers alongside a single writer, read
    queries no longer block behind slow writes (and vice-versa).

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
        self._read_conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._read_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Whether the manager currently holds an open connection."""
        return self._conn is not None

    async def _open_connection(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    async def connect(self) -> None:
        """Open both read and write connections and run pending migrations.

        Creates parent directories if the path is a file (not :memory:).
        Enables WAL journal mode and foreign keys on both connections.

        For ``:memory:`` databases, read and write share the same connection
        (since each in-memory connection is an isolated database).
        """
        async with self._lock:
            if self._conn is not None:
                return

            if self._db_path != ":memory:":
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

            self._conn = await self._open_connection()

            if self._db_path == ":memory:":
                self._read_conn = self._conn
                self._read_lock = self._write_lock
            else:
                self._read_conn = await self._open_connection()

            if self._migration_runner is not None:
                await self._migration_runner.run_pending(self._conn)

    async def close(self) -> None:
        """Close both database connections."""
        async with self._lock:
            if self._read_conn is not None and self._read_conn is not self._conn:
                await self._read_conn.close()
            self._read_conn = None
            if self._conn is not None:
                await self._conn.close()
                self._conn = None

    def _require_connection(self) -> aiosqlite.Connection:
        """Return the active write connection or raise."""
        if self._conn is None:
            raise ConnectionError("Database not connected. Call connect() first.")
        return self._conn

    def _require_read_connection(self) -> aiosqlite.Connection:
        """Return the active read connection or raise."""
        if self._read_conn is None:
            raise ConnectionError("Database not connected. Call connect() first.")
        return self._read_conn

    async def query(
        self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()
    ) -> list[aiosqlite.Row]:
        """Execute a read-only SQL query (SELECT) on the dedicated read connection.

        Runs concurrently with writes thanks to WAL mode, so reads never
        block behind long-running INSERT/DELETE batches.
        """
        async with self._read_lock:
            conn = self._require_read_connection()
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            return cast(list[aiosqlite.Row], rows)

    async def execute(
        self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()
    ) -> list[aiosqlite.Row]:
        """Execute a SQL statement (INSERT/UPDATE/DELETE) and commit.

        Serialized via ``_write_lock`` to prevent concurrent writes on
        the same connection.
        """
        async with self._write_lock:
            conn = self._require_connection()
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            await conn.commit()
            return cast(list[aiosqlite.Row], rows)

    async def execute_many(self, sql: str, params_list: list[tuple[Any, ...]]) -> None:
        """Execute a SQL statement against each parameter set.

        Args:
            sql: SQL statement with ``?`` placeholders.
            params_list: List of parameter tuples.
        """
        async with self._write_lock:
            conn = self._require_connection()
            await conn.executemany(sql, params_list)
            await conn.commit()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Yield the underlying write connection for advanced use.

        The connection is committed on successful exit and rolled back on
        exception. Callers should prefer ``execute`` / ``execute_many`` for
        simple operations.

        Acquires ``_write_lock`` for the duration of the block to prevent
        concurrent writes on the same connection.
        """
        async with self._write_lock:
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
