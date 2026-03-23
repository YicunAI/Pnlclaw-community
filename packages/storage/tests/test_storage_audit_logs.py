"""Tests for AuditLogRepository."""

from __future__ import annotations

import pytest
import pytest_asyncio

from pnlclaw_storage.migrations import MigrationRunner
from pnlclaw_storage.migrations_pkg import ALL_MIGRATIONS
from pnlclaw_storage.repositories.audit_logs import AuditLogRepository
from pnlclaw_storage.sqlite import AsyncSQLiteManager


@pytest_asyncio.fixture
async def repo():
    runner = MigrationRunner(ALL_MIGRATIONS)
    async with AsyncSQLiteManager(":memory:", migration_runner=runner) as db:
        yield AuditLogRepository(db)


@pytest.mark.asyncio
async def test_append_and_query(repo: AuditLogRepository):
    event_id = await repo.append({
        "event_type": "order_placed",
        "severity": "info",
        "actor": "user:alice",
        "action": "place_order",
        "resource": "paper_account:a1",
        "outcome": "success",
        "details": {"symbol": "BTC/USDT", "quantity": 0.5},
    })
    assert event_id  # non-empty string

    logs = await repo.query()
    assert len(logs) == 1
    assert logs[0]["event_type"] == "order_placed"
    assert logs[0]["details"]["symbol"] == "BTC/USDT"


@pytest.mark.asyncio
async def test_append_auto_generates_id(repo: AuditLogRepository):
    id1 = await repo.append({"event_type": "test"})
    id2 = await repo.append({"event_type": "test"})
    assert id1 != id2


@pytest.mark.asyncio
async def test_append_with_explicit_id(repo: AuditLogRepository):
    event_id = await repo.append({"id": "custom-id", "event_type": "test"})
    assert event_id == "custom-id"


@pytest.mark.asyncio
async def test_query_by_event_type(repo: AuditLogRepository):
    await repo.append({"event_type": "order_placed"})
    await repo.append({"event_type": "config_changed"})
    await repo.append({"event_type": "order_placed"})

    orders = await repo.query(event_type="order_placed")
    assert len(orders) == 2
    assert all(e["event_type"] == "order_placed" for e in orders)


@pytest.mark.asyncio
async def test_query_since(repo: AuditLogRepository):
    await repo.append({"event_type": "old", "timestamp": "2025-01-01T00:00:00"})
    await repo.append({"event_type": "new", "timestamp": "2025-06-01T00:00:00"})

    results = await repo.query(since="2025-03-01T00:00:00")
    assert len(results) == 1
    assert results[0]["event_type"] == "new"


@pytest.mark.asyncio
async def test_query_limit(repo: AuditLogRepository):
    for i in range(10):
        await repo.append({"event_type": "bulk", "timestamp": f"2025-01-{i+1:02d}T00:00:00"})

    results = await repo.query(limit=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_query_newest_first(repo: AuditLogRepository):
    await repo.append({"event_type": "a", "timestamp": "2025-01-01T00:00:00"})
    await repo.append({"event_type": "b", "timestamp": "2025-06-01T00:00:00"})
    await repo.append({"event_type": "c", "timestamp": "2025-03-01T00:00:00"})

    results = await repo.query()
    types = [r["event_type"] for r in results]
    assert types == ["b", "c", "a"]


@pytest.mark.asyncio
async def test_query_combined_filters(repo: AuditLogRepository):
    await repo.append({"event_type": "order", "timestamp": "2025-01-01T00:00:00"})
    await repo.append({"event_type": "order", "timestamp": "2025-06-01T00:00:00"})
    await repo.append({"event_type": "config", "timestamp": "2025-06-01T00:00:00"})

    results = await repo.query(event_type="order", since="2025-03-01T00:00:00")
    assert len(results) == 1
    assert results[0]["event_type"] == "order"


@pytest.mark.asyncio
async def test_defaults(repo: AuditLogRepository):
    await repo.append({"event_type": "minimal"})
    logs = await repo.query()
    assert logs[0]["severity"] == "info"
    assert logs[0]["actor"] == ""
    assert logs[0]["details"] == {}
