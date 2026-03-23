"""Tests for PaperAccountRepository."""

from __future__ import annotations

import pytest
import pytest_asyncio

from pnlclaw_storage.migrations import MigrationRunner
from pnlclaw_storage.migrations_pkg import ALL_MIGRATIONS
from pnlclaw_storage.repositories.paper_accounts import PaperAccountRepository
from pnlclaw_storage.sqlite import AsyncSQLiteManager


@pytest_asyncio.fixture
async def repo():
    runner = MigrationRunner(ALL_MIGRATIONS)
    async with AsyncSQLiteManager(":memory:", migration_runner=runner) as db:
        yield PaperAccountRepository(db)


# ------------------------------------------------------------------
# Accounts
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_get_account(repo: PaperAccountRepository):
    acct = {
        "id": "acct-001",
        "name": "Demo",
        "initial_balance": 50000.0,
        "current_balance": 50000.0,
    }
    saved_id = await repo.save_account(acct)
    assert saved_id == "acct-001"

    loaded = await repo.get_account("acct-001")
    assert loaded is not None
    assert loaded["name"] == "Demo"
    assert loaded["initial_balance"] == 50000.0
    assert loaded["status"] == "active"


@pytest.mark.asyncio
async def test_get_account_nonexistent(repo: PaperAccountRepository):
    assert await repo.get_account("nope") is None


@pytest.mark.asyncio
async def test_save_account_upsert(repo: PaperAccountRepository):
    await repo.save_account({"id": "a1", "name": "V1", "initial_balance": 10000.0})
    await repo.save_account(
        {"id": "a1", "name": "V2", "initial_balance": 10000.0, "current_balance": 9500.0}
    )
    loaded = await repo.get_account("a1")
    assert loaded is not None
    assert loaded["name"] == "V2"
    assert loaded["current_balance"] == 9500.0


# ------------------------------------------------------------------
# Orders
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_get_orders(repo: PaperAccountRepository):
    await repo.save_account({"id": "a1", "name": "Test"})
    await repo.save_order(
        {
            "id": "ord-001",
            "account_id": "a1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "market",
            "quantity": 0.5,
        }
    )
    orders = await repo.get_orders("a1")
    assert len(orders) == 1
    assert orders[0]["symbol"] == "BTC/USDT"
    assert orders[0]["status"] == "created"


@pytest.mark.asyncio
async def test_get_orders_with_status_filter(repo: PaperAccountRepository):
    await repo.save_account({"id": "a1", "name": "Test"})
    await repo.save_order(
        {
            "id": "o1",
            "account_id": "a1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "market",
            "quantity": 1.0,
            "status": "filled",
        }
    )
    await repo.save_order(
        {
            "id": "o2",
            "account_id": "a1",
            "symbol": "ETH/USDT",
            "side": "sell",
            "type": "limit",
            "quantity": 10.0,
            "status": "created",
        }
    )

    filled = await repo.get_orders("a1", status="filled")
    assert len(filled) == 1
    assert filled[0]["id"] == "o1"

    all_orders = await repo.get_orders("a1")
    assert len(all_orders) == 2


@pytest.mark.asyncio
async def test_save_order_upsert(repo: PaperAccountRepository):
    await repo.save_account({"id": "a1", "name": "Test"})
    await repo.save_order(
        {
            "id": "o1",
            "account_id": "a1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "market",
            "quantity": 1.0,
            "status": "created",
        }
    )
    await repo.save_order(
        {
            "id": "o1",
            "account_id": "a1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "market",
            "quantity": 1.0,
            "status": "filled",
            "filled_quantity": 1.0,
            "avg_fill_price": 67000.0,
        }
    )
    orders = await repo.get_orders("a1")
    assert len(orders) == 1
    assert orders[0]["status"] == "filled"
    assert orders[0]["avg_fill_price"] == 67000.0


# ------------------------------------------------------------------
# Positions
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_get_positions(repo: PaperAccountRepository):
    await repo.save_account({"id": "a1", "name": "Test"})
    await repo.save_position(
        {
            "id": "pos-001",
            "account_id": "a1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "quantity": 0.5,
            "avg_entry_price": 67000.0,
            "unrealized_pnl": 150.0,
        }
    )

    positions = await repo.get_positions("a1")
    assert len(positions) == 1
    assert positions[0]["symbol"] == "BTC/USDT"
    assert positions[0]["quantity"] == 0.5
    assert positions[0]["unrealized_pnl"] == 150.0


@pytest.mark.asyncio
async def test_save_position_upsert(repo: PaperAccountRepository):
    await repo.save_account({"id": "a1", "name": "Test"})
    await repo.save_position(
        {
            "id": "p1",
            "account_id": "a1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "quantity": 0.5,
            "avg_entry_price": 67000.0,
        }
    )
    await repo.save_position(
        {
            "id": "p1",
            "account_id": "a1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "quantity": 0.8,
            "avg_entry_price": 66500.0,
            "unrealized_pnl": 200.0,
        }
    )

    positions = await repo.get_positions("a1")
    assert len(positions) == 1
    assert positions[0]["quantity"] == 0.8
    assert positions[0]["avg_entry_price"] == 66500.0


@pytest.mark.asyncio
async def test_get_positions_empty(repo: PaperAccountRepository):
    await repo.save_account({"id": "a1", "name": "Test"})
    assert await repo.get_positions("a1") == []
