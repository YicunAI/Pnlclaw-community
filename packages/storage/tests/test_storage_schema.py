"""Tests for v001 initial schema migration."""

from __future__ import annotations

import aiosqlite
import pytest
import pytest_asyncio

from pnlclaw_storage.migrations import MigrationRunner
from pnlclaw_storage.migrations_pkg import ALL_MIGRATIONS


@pytest_asyncio.fixture
async def conn():
    c = await aiosqlite.connect(":memory:")
    yield c
    await c.close()


@pytest_asyncio.fixture
async def migrated_conn(conn: aiosqlite.Connection):
    runner = MigrationRunner(ALL_MIGRATIONS)
    await runner.run_pending(conn)
    return conn


EXPECTED_TABLES = [
    "strategies",
    "backtests",
    "paper_accounts",
    "paper_orders",
    "paper_positions",
    "audit_logs",
    "strategy_versions",
    "strategy_deployments",
]


@pytest.mark.asyncio
async def test_all_tables_created(migrated_conn: aiosqlite.Connection):
    cursor = await migrated_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in await cursor.fetchall()}
    for table in EXPECTED_TABLES:
        assert table in tables, f"Table {table} not created"


@pytest.mark.asyncio
async def test_idempotent_migration(conn: aiosqlite.Connection):
    runner = MigrationRunner(ALL_MIGRATIONS)
    first = await runner.run_pending(conn)
    second = await runner.run_pending(conn)
    assert len(first) == len(ALL_MIGRATIONS)
    assert len(second) == 0


@pytest.mark.asyncio
async def test_strategies_columns(migrated_conn: aiosqlite.Connection):
    cursor = await migrated_conn.execute("PRAGMA table_info(strategies)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert cols >= {"id", "name", "type", "config_json", "created_at", "updated_at", "version", "lifecycle_state"}




@pytest.mark.asyncio
async def test_backtests_columns_include_strategy_version(migrated_conn: aiosqlite.Connection):
    cursor = await migrated_conn.execute("PRAGMA table_info(backtests)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert "strategy_version" in cols

    cursor = await migrated_conn.execute("PRAGMA foreign_key_list(backtests)")
    fks = await cursor.fetchall()
    assert any(row[2] == "strategies" for row in fks)


@pytest.mark.asyncio
async def test_paper_orders_foreign_key(migrated_conn: aiosqlite.Connection):
    cursor = await migrated_conn.execute("PRAGMA foreign_key_list(paper_orders)")
    fks = await cursor.fetchall()
    assert any(row[2] == "paper_accounts" for row in fks)


@pytest.mark.asyncio
async def test_audit_logs_columns(migrated_conn: aiosqlite.Connection):
    cursor = await migrated_conn.execute("PRAGMA table_info(audit_logs)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert cols >= {
        "id",
        "timestamp",
        "event_type",
        "severity",
        "actor",
        "action",
        "resource",
        "outcome",
        "details_json",
    }


@pytest.mark.asyncio
async def test_indexes_exist(migrated_conn: aiosqlite.Connection):
    cursor = await migrated_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )
    indexes = {row[0] for row in await cursor.fetchall()}
    expected = {
        "idx_strategies_name",
        "idx_backtests_strategy_id",
        "idx_paper_orders_account_id",
        "idx_paper_positions_account_id",
        "idx_audit_logs_timestamp",
        "idx_audit_logs_event_type",
    }
    assert expected <= indexes


@pytest.mark.asyncio
async def test_v02_alter_table_add_column(migrated_conn: aiosqlite.Connection):
    """Verify that adding a tenant_id column works without table rebuild."""
    for table in EXPECTED_TABLES:
        await migrated_conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT")
    await migrated_conn.commit()

    # Verify column was added
    cursor = await migrated_conn.execute("PRAGMA table_info(strategies)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert "tenant_id" in cols
