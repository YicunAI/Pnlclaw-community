"""Tests for StrategyRepository."""

from __future__ import annotations

import pytest
import pytest_asyncio

from pnlclaw_storage.migrations import MigrationRunner
from pnlclaw_storage.migrations_pkg import ALL_MIGRATIONS
from pnlclaw_storage.repositories.strategies import StrategyRepository
from pnlclaw_storage.sqlite import AsyncSQLiteManager
from pnlclaw_types.strategy import StrategyConfig, StrategyType


def _make_strategy(id: str = "strat-001", name: str = "Test SMA") -> StrategyConfig:
    return StrategyConfig(
        id=id,
        name=name,
        type=StrategyType.SMA_CROSS,
        symbols=["BTC/USDT"],
        interval="1h",
        parameters={"sma_short": 10, "sma_long": 50},
        tags=["trend", "btc"],
        source="user",
        version=1,
        lifecycle_state="draft",
    )


@pytest_asyncio.fixture
async def repo():
    runner = MigrationRunner(ALL_MIGRATIONS)
    async with AsyncSQLiteManager(":memory:", migration_runner=runner) as db:
        yield StrategyRepository(db)


@pytest.mark.asyncio
async def test_save_and_get(repo: StrategyRepository):
    strategy = _make_strategy()
    result_id = await repo.save(strategy)
    assert result_id == "strat-001"

    loaded = await repo.get("strat-001")
    assert loaded is not None
    assert loaded.id == "strat-001"
    assert loaded.name == "Test SMA"
    assert loaded.parameters["sma_short"] == 10


@pytest.mark.asyncio
async def test_get_nonexistent(repo: StrategyRepository):
    assert await repo.get("nonexistent") is None


@pytest.mark.asyncio
async def test_save_upsert(repo: StrategyRepository):
    await repo.save(_make_strategy(name="Original"))
    await repo.save(_make_strategy(name="Updated"))

    loaded = await repo.get("strat-001")
    assert loaded is not None
    assert loaded.name == "Updated"


@pytest.mark.asyncio
async def test_list(repo: StrategyRepository):
    await repo.save(_make_strategy("s1", "First"))
    await repo.save(_make_strategy("s2", "Second"))
    await repo.save(_make_strategy("s3", "Third"))

    results = await repo.list(limit=2)
    assert len(results) == 2

    all_results = await repo.list()
    assert len(all_results) == 3


@pytest.mark.asyncio
async def test_list_with_offset(repo: StrategyRepository):
    await repo.save(_make_strategy("s1", "First"))
    await repo.save(_make_strategy("s2", "Second"))
    await repo.save(_make_strategy("s3", "Third"))

    page2 = await repo.list(limit=2, offset=2)
    assert len(page2) == 1




@pytest.mark.asyncio
async def test_list_filter_by_tags(repo: StrategyRepository):
    await repo.save(_make_strategy("s1", "BTC Trend"))
    await repo.save(
        StrategyConfig(
            id="s2",
            name="ETH Reversal",
            type=StrategyType.RSI_REVERSAL,
            symbols=["ETH/USDT"],
            interval="1h",
            tags=["mean-reversion", "eth"],
            source="ai_agent",
        )
    )

    results = await repo.list(tags=["btc"])
    assert len(results) == 1
    assert results[0].id == "s1"


@pytest.mark.asyncio
async def test_list_filter_by_source(repo: StrategyRepository):
    await repo.save(_make_strategy("s1", "Manual"))
    await repo.save(
        StrategyConfig(
            id="s2",
            name="Generated",
            type=StrategyType.RSI_REVERSAL,
            symbols=["ETH/USDT"],
            interval="1h",
            source="ai_agent",
        )
    )

    results = await repo.list(source="ai_agent")
    assert len(results) == 1
    assert results[0].id == "s2"

    await repo.save(_make_strategy())
    assert await repo.delete("strat-001") is True
    assert await repo.get("strat-001") is None


@pytest.mark.asyncio
async def test_delete_nonexistent(repo: StrategyRepository):
    assert await repo.delete("nonexistent") is False


@pytest.mark.asyncio
async def test_roundtrip_preserves_all_fields(repo: StrategyRepository):
    strategy = StrategyConfig(
        id="full-001",
        name="Full Config",
        type=StrategyType.RSI_REVERSAL,
        description="A test strategy",
        symbols=["ETH/USDT", "BTC/USDT"],
        interval="4h",
        parameters={"rsi_period": 14, "overbought": 70},
        entry_rules={"condition": "rsi < 30"},
        exit_rules={"condition": "rsi > 70"},
        risk_params={"stop_loss_pct": 0.03},
        tags=["mean-reversion"],
        source="ai_agent",
        version=3,
        lifecycle_state="confirmed",
    )
    await repo.save(strategy)
    loaded = await repo.get("full-001")
    assert loaded is not None
    assert loaded.description == "A test strategy"
    assert loaded.symbols == ["ETH/USDT", "BTC/USDT"]
    assert loaded.entry_rules == {"condition": "rsi < 30"}
    assert loaded.risk_params == {"stop_loss_pct": 0.03}
    assert loaded.tags == ["mean-reversion"]
    assert loaded.source == "ai_agent"
    assert loaded.version == 3
    assert loaded.lifecycle_state == "confirmed"
