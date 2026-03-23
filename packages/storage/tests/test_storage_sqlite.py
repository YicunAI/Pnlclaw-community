"""Tests for AsyncSQLiteManager."""

from __future__ import annotations

import pytest
import pytest_asyncio

from pnlclaw_storage.migrations import Migration, MigrationRunner
from pnlclaw_storage.sqlite import AsyncSQLiteManager, ConnectionError


@pytest_asyncio.fixture
async def db():
    """Provide an in-memory AsyncSQLiteManager."""
    manager = AsyncSQLiteManager(db_path=":memory:")
    await manager.connect()
    yield manager
    await manager.close()


@pytest.mark.asyncio
async def test_connect_and_close():
    mgr = AsyncSQLiteManager(db_path=":memory:")
    assert not mgr.is_connected
    await mgr.connect()
    assert mgr.is_connected
    await mgr.close()
    assert not mgr.is_connected


@pytest.mark.asyncio
async def test_context_manager():
    async with AsyncSQLiteManager(db_path=":memory:") as mgr:
        assert mgr.is_connected
    assert not mgr.is_connected


@pytest.mark.asyncio
async def test_execute_create_and_query(db: AsyncSQLiteManager):
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    await db.execute("INSERT INTO t (val) VALUES (?)", ("hello",))
    rows = await db.execute("SELECT val FROM t")
    assert len(rows) == 1
    assert rows[0]["val"] == "hello"


@pytest.mark.asyncio
async def test_execute_many(db: AsyncSQLiteManager):
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    await db.execute_many(
        "INSERT INTO t (val) VALUES (?)",
        [("a",), ("b",), ("c",)],
    )
    rows = await db.execute("SELECT val FROM t ORDER BY val")
    assert [r["val"] for r in rows] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_connection_context_manager(db: AsyncSQLiteManager):
    async with db.connection() as conn:
        await conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        await conn.execute("INSERT INTO t (id) VALUES (1)")
    rows = await db.execute("SELECT id FROM t")
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_connection_context_manager_rollback(db: AsyncSQLiteManager):
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    await db.execute("INSERT INTO t (id, val) VALUES (1, 'before')")

    with pytest.raises(ValueError, match="boom"):
        async with db.connection() as conn:
            await conn.execute("UPDATE t SET val = 'after' WHERE id = 1")
            raise ValueError("boom")

    rows = await db.execute("SELECT val FROM t WHERE id = 1")
    assert rows[0]["val"] == "before"


@pytest.mark.asyncio
async def test_wal_mode_enabled(db: AsyncSQLiteManager):
    rows = await db.execute("PRAGMA journal_mode")
    # :memory: databases report "memory" for journal mode
    assert rows[0][0] in ("wal", "memory")


@pytest.mark.asyncio
async def test_foreign_keys_enabled(db: AsyncSQLiteManager):
    rows = await db.execute("PRAGMA foreign_keys")
    assert rows[0][0] == 1


@pytest.mark.asyncio
async def test_error_when_not_connected():
    mgr = AsyncSQLiteManager(db_path=":memory:")
    with pytest.raises(ConnectionError, match="not connected"):
        await mgr.execute("SELECT 1")




@pytest.mark.asyncio
async def test_default_migrations_run_without_runner():
    async with AsyncSQLiteManager(db_path=":memory:") as mgr:
        rows = await mgr.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='strategies'"
        )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_custom_runner_overrides_default():
    async def _create_demo(conn):
        await conn.execute("CREATE TABLE demo_custom (id INTEGER PRIMARY KEY)")

    custom_runner = MigrationRunner(
        [Migration(id="v900", version=900, description="demo", apply=_create_demo)]
    )
    async with AsyncSQLiteManager(db_path=":memory:", migration_runner=custom_runner) as mgr:
        custom = await mgr.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='demo_custom'"
        )
        strategies = await mgr.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='strategies'"
        )
    assert len(custom) == 1
    assert strategies == []
