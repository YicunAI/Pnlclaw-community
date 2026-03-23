"""Tests for the declarative migration framework."""

from __future__ import annotations

import aiosqlite
import pytest
import pytest_asyncio

from pnlclaw_storage.migrations import Migration, MigrationRunner


async def _create_demo_table(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS demo (id INTEGER PRIMARY KEY, name TEXT)"
    )


async def _add_column(conn: aiosqlite.Connection) -> None:
    await conn.execute("ALTER TABLE demo ADD COLUMN email TEXT")


async def _create_then_fail(conn: aiosqlite.Connection) -> None:
    await conn.execute("CREATE TABLE tx_fail (id INTEGER PRIMARY KEY)")
    raise RuntimeError("boom")


@pytest_asyncio.fixture
async def conn():
    c = await aiosqlite.connect(":memory:")
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_run_pending_executes_migrations(conn: aiosqlite.Connection):
    runner = MigrationRunner([
        Migration(id="v001", version=1, description="create demo", apply=_create_demo_table),
    ])
    executed = await runner.run_pending(conn)
    assert executed == ["create demo"]

    # Verify table exists
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='demo'"
    )
    assert (await cursor.fetchone()) is not None


@pytest.mark.asyncio
async def test_idempotent_run(conn: aiosqlite.Connection):
    runner = MigrationRunner([
        Migration(id="v001", version=1, description="create demo", apply=_create_demo_table),
    ])
    first = await runner.run_pending(conn)
    second = await runner.run_pending(conn)
    assert first == ["create demo"]
    assert second == []


@pytest.mark.asyncio
async def test_version_ordering(conn: aiosqlite.Connection):
    # Register out of order
    runner = MigrationRunner([
        Migration(id="v002", version=2, description="add email", apply=_add_column),
        Migration(id="v001", version=1, description="create demo", apply=_create_demo_table),
    ])
    executed = await runner.run_pending(conn)
    assert executed == ["create demo", "add email"]


@pytest.mark.asyncio
async def test_register_after_init(conn: aiosqlite.Connection):
    runner = MigrationRunner()
    runner.register(
        Migration(id="v001", version=1, description="create demo", apply=_create_demo_table)
    )
    executed = await runner.run_pending(conn)
    assert executed == ["create demo"]


@pytest.mark.asyncio
async def test_partial_run_resumes(conn: aiosqlite.Connection):
    runner1 = MigrationRunner([
        Migration(id="v001", version=1, description="create demo", apply=_create_demo_table),
    ])
    await runner1.run_pending(conn)

    # New runner with both migrations
    runner2 = MigrationRunner([
        Migration(id="v001", version=1, description="create demo", apply=_create_demo_table),
        Migration(id="v002", version=2, description="add email", apply=_add_column),
    ])
    executed = await runner2.run_pending(conn)
    assert executed == ["add email"]


@pytest.mark.asyncio
async def test_migrations_table_records(conn: aiosqlite.Connection):
    runner = MigrationRunner([
        Migration(id="v001", version=1, description="create demo", apply=_create_demo_table),
    ])
    await runner.run_pending(conn)

    cursor = await conn.execute(
        "SELECT id, version, description FROM _migrations"
    )
    rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "v001"
    assert rows[0][1] == 1
    assert rows[0][2] == "create demo"


@pytest.mark.asyncio
async def test_failed_migration_rolls_back(conn: aiosqlite.Connection):
    runner = MigrationRunner([
        Migration(id="v001", version=1, description="fails", apply=_create_then_fail),
    ])

    with pytest.raises(RuntimeError, match="boom"):
        await runner.run_pending(conn)

    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tx_fail'"
    )
    assert (await cursor.fetchone()) is None

    cursor = await conn.execute("SELECT id FROM _migrations WHERE id='v001'")
    assert (await cursor.fetchone()) is None
