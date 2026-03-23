"""Tests for BacktestRepository."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from pnlclaw_types.strategy import (
    BacktestMetrics,
    BacktestResult,
    StrategyConfig,
    StrategyType,
)

from pnlclaw_storage.migrations import MigrationRunner
from pnlclaw_storage.migrations_pkg import ALL_MIGRATIONS
from pnlclaw_storage.repositories.backtests import BacktestRepository
from pnlclaw_storage.repositories.strategies import StrategyRepository
from pnlclaw_storage.sqlite import AsyncSQLiteManager


_METRICS = BacktestMetrics(
    total_return=0.15,
    annual_return=0.45,
    sharpe_ratio=1.8,
    max_drawdown=-0.08,
    win_rate=0.55,
    profit_factor=1.6,
    total_trades=42,
)


def _make_result(id: str = "bt-001", strategy_id: str = "strat-001") -> BacktestResult:
    return BacktestResult(
        id=id,
        strategy_id=strategy_id,
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2025, 3, 31, tzinfo=timezone.utc),
        metrics=_METRICS,
        equity_curve=[10000.0, 10050.0, 10200.0, 10500.0],
        trades_count=42,
        created_at=1711000000000,
    )


@pytest_asyncio.fixture
async def repos():
    runner = MigrationRunner(ALL_MIGRATIONS)
    async with AsyncSQLiteManager(":memory:", migration_runner=runner) as db:
        strat_repo = StrategyRepository(db)
        bt_repo = BacktestRepository(db)

        # Create a strategy to satisfy foreign key
        await strat_repo.save(
            StrategyConfig(
                id="strat-001",
                name="Test",
                type=StrategyType.SMA_CROSS,
                symbols=["BTC/USDT"],
                interval="1h",
            )
        )
        yield strat_repo, bt_repo


@pytest.mark.asyncio
async def test_save_and_get(repos):
    _, bt_repo = repos
    result = _make_result()
    saved_id = await bt_repo.save(result)
    assert saved_id == "bt-001"

    loaded = await bt_repo.get("bt-001")
    assert loaded is not None
    assert loaded.strategy_id == "strat-001"
    assert loaded.metrics.sharpe_ratio == 1.8
    assert loaded.equity_curve == [10000.0, 10050.0, 10200.0, 10500.0]
    assert loaded.trades_count == 42


@pytest.mark.asyncio
async def test_get_nonexistent(repos):
    _, bt_repo = repos
    assert await bt_repo.get("nonexistent") is None


@pytest.mark.asyncio
async def test_list_by_strategy(repos):
    _, bt_repo = repos
    await bt_repo.save(_make_result("bt-001"))
    await bt_repo.save(_make_result("bt-002"))
    await bt_repo.save(_make_result("bt-003"))

    results = await bt_repo.list_by_strategy("strat-001")
    assert len(results) == 3


@pytest.mark.asyncio
async def test_list_by_strategy_limit(repos):
    _, bt_repo = repos
    await bt_repo.save(_make_result("bt-001"))
    await bt_repo.save(_make_result("bt-002"))
    await bt_repo.save(_make_result("bt-003"))

    results = await bt_repo.list_by_strategy("strat-001", limit=2)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_list_by_strategy_empty(repos):
    _, bt_repo = repos
    results = await bt_repo.list_by_strategy("nonexistent")
    assert results == []


@pytest.mark.asyncio
async def test_metrics_roundtrip(repos):
    _, bt_repo = repos
    await bt_repo.save(_make_result())
    loaded = await bt_repo.get("bt-001")
    assert loaded is not None
    assert loaded.metrics.total_return == 0.15
    assert loaded.metrics.max_drawdown == -0.08
    assert loaded.metrics.win_rate == 0.55
    assert loaded.metrics.profit_factor == 1.6


@pytest.mark.asyncio
async def test_dates_roundtrip(repos):
    _, bt_repo = repos
    await bt_repo.save(_make_result())
    loaded = await bt_repo.get("bt-001")
    assert loaded is not None
    assert loaded.start_date.year == 2025
    assert loaded.start_date.month == 1
    assert loaded.end_date.month == 3
