"""Tests for BacktestRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from pnlclaw_storage.migrations import MigrationRunner
from pnlclaw_storage.migrations_pkg import ALL_MIGRATIONS
from pnlclaw_storage.repositories.backtests import BacktestRepository
from pnlclaw_storage.repositories.strategies import StrategyRepository
from pnlclaw_storage.sqlite import AsyncSQLiteManager
from pnlclaw_types.strategy import (
    BacktestMetrics,
    BacktestResult,
    StrategyConfig,
    StrategyType,
)

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
        strategy_version=2,
        symbol="BTC/USDT",
        interval="1h",
        start_date=datetime(2025, 1, 1, tzinfo=UTC),
        end_date=datetime(2025, 3, 31, tzinfo=UTC),
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
    assert loaded.strategy_version == 2
    assert loaded.symbol == "BTC/USDT"
    assert loaded.interval == "1h"
    assert loaded.equity_curve == [10000.0, 10050.0, 10200.0, 10500.0]
    assert loaded.trades_count == 42
    assert loaded.created_at == result.created_at


@pytest.mark.asyncio
async def test_get_nonexistent(repos):
    _, bt_repo = repos
    assert await bt_repo.get("nonexistent") is None




@pytest.mark.asyncio
async def test_list_all(repos):
    _, bt_repo = repos
    await bt_repo.save(_make_result("bt-001"))
    await bt_repo.save(_make_result("bt-002"))

    results = await bt_repo.list_all(limit=10, offset=0)
    assert len(results) == 2

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


@pytest.mark.asyncio
async def test_created_at_roundtrip(repos):
    _, bt_repo = repos
    original = _make_result("bt-created-at")
    await bt_repo.save(original)

    loaded = await bt_repo.get("bt-created-at")
    assert loaded is not None
    assert loaded.created_at == original.created_at


@pytest.mark.asyncio
async def test_curves_and_trades_roundtrip(repos):
    """buy_hold_curve, drawdown_curve, and trades should persist and reload."""
    _, bt_repo = repos
    result = BacktestResult(
        id="bt-curves",
        strategy_id="strat-001",
        strategy_version=1,
        start_date=datetime(2025, 1, 1, tzinfo=UTC),
        end_date=datetime(2025, 3, 31, tzinfo=UTC),
        metrics=_METRICS,
        equity_curve=[10000.0, 10200.0, 10500.0, 10100.0],
        buy_hold_curve=[10000.0, 10100.0, 10300.0, 10400.0],
        drawdown_curve=[0.0, 0.0, 0.0, -0.038],
        trades=[{"side": "long", "entry_price": 100, "exit_price": 105, "pnl": 50}],
        trades_count=1,
        created_at=1711000000000,
    )
    await bt_repo.save(result)

    loaded = await bt_repo.get("bt-curves")
    assert loaded is not None
    assert loaded.equity_curve == [10000.0, 10200.0, 10500.0, 10100.0]
    assert loaded.buy_hold_curve == [10000.0, 10100.0, 10300.0, 10400.0]
    assert loaded.drawdown_curve == [0.0, 0.0, 0.0, -0.038]
    assert len(loaded.trades) == 1
    assert loaded.trades[0]["pnl"] == 50


@pytest.mark.asyncio
async def test_symbol_interval_roundtrip(repos):
    """symbol and interval should persist and reload correctly."""
    _, bt_repo = repos
    result = BacktestResult(
        id="bt-sym",
        strategy_id="strat-001",
        strategy_version=1,
        symbol="ETH/USDT",
        interval="4h",
        start_date=datetime(2025, 1, 1, tzinfo=UTC),
        end_date=datetime(2025, 3, 31, tzinfo=UTC),
        metrics=_METRICS,
        equity_curve=[10000.0, 10200.0],
        trades_count=0,
        created_at=1711000000000,
    )
    await bt_repo.save(result)

    loaded = await bt_repo.get("bt-sym")
    assert loaded is not None
    assert loaded.symbol == "ETH/USDT"
    assert loaded.interval == "4h"


@pytest.mark.asyncio
async def test_empty_curves_recomputed(repos):
    """When buy_hold_curve and drawdown_curve are empty, they should be recomputed from equity_curve."""
    _, bt_repo = repos
    result = BacktestResult(
        id="bt-recompute",
        strategy_id="strat-001",
        strategy_version=1,
        start_date=datetime(2025, 1, 1, tzinfo=UTC),
        end_date=datetime(2025, 3, 31, tzinfo=UTC),
        metrics=_METRICS,
        equity_curve=[10000.0, 10200.0, 10500.0, 10100.0],
        trades_count=0,
        created_at=1711000000000,
    )
    await bt_repo.save(result)

    loaded = await bt_repo.get("bt-recompute")
    assert loaded is not None
    assert len(loaded.drawdown_curve) == 4
    assert loaded.drawdown_curve[0] == 0.0
    assert loaded.drawdown_curve[3] < 0
    assert len(loaded.buy_hold_curve) == 4
