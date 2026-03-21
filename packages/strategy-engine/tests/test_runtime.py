"""Tests for S2-E07: strategy runtime."""

from __future__ import annotations

import pytest

from pnlclaw_strategy.compiler import compile
from pnlclaw_strategy.models import (
    ConditionRule,
    EngineStrategyConfig,
    EntryRules,
    ExitRules,
    RiskParams,
)
from pnlclaw_strategy.runtime import StrategyRuntime
from pnlclaw_types.market import KlineEvent
from pnlclaw_types.strategy import Signal
from pnlclaw_types.trading import OrderSide


def _make_kline(
    close: float,
    timestamp: int = 0,
    closed: bool = True,
    symbol: str = "BTC/USDT",
) -> KlineEvent:
    """Helper to create a KlineEvent."""
    return KlineEvent(
        exchange="binance",
        symbol=symbol,
        timestamp=timestamp,
        interval="1h",
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=100.0,
        closed=closed,
    )


def _sma_cross_compiled():
    """Create a compiled SMA cross strategy for testing."""
    entry_rule = ConditionRule(
        indicator="sma",
        params={"period": 5},
        operator="crosses_above",
        comparator={"indicator": "sma", "params": {"period": 10}},
    )
    exit_rule = ConditionRule(
        indicator="sma",
        params={"period": 5},
        operator="crosses_below",
        comparator={"indicator": "sma", "params": {"period": 10}},
    )
    config = EngineStrategyConfig(
        id="sma-cross-test",
        name="SMA Cross Test",
        type="sma_cross",
        symbols=["BTC/USDT"],
        interval="1h",
        parsed_entry_rules=EntryRules(long=[entry_rule]),
        parsed_exit_rules=ExitRules(close_long=[exit_rule]),
    )
    return compile(config)


def _rsi_compiled():
    """Create a compiled RSI reversal strategy for testing."""
    entry_rule = ConditionRule(
        indicator="rsi",
        params={"period": 14},
        operator="less_than",
        comparator=30.0,
    )
    exit_rule = ConditionRule(
        indicator="rsi",
        params={"period": 14},
        operator="greater_than",
        comparator=70.0,
    )
    config = EngineStrategyConfig(
        id="rsi-test",
        name="RSI Test",
        type="rsi_reversal",
        symbols=["BTC/USDT"],
        interval="1h",
        parsed_entry_rules=EntryRules(long=[entry_rule]),
        parsed_exit_rules=ExitRules(close_long=[exit_rule]),
    )
    return compile(config)


class TestStrategyRuntime:
    """Test StrategyRuntime kline processing."""

    def test_ignores_unclosed_kline(self) -> None:
        rt = StrategyRuntime(_sma_cross_compiled())
        signal = rt.on_kline(_make_kline(100.0, closed=False))
        assert signal is None
        assert rt.bar_count == 0

    def test_bar_accumulation(self) -> None:
        rt = StrategyRuntime(_sma_cross_compiled())
        for i in range(10):
            rt.on_kline(_make_kline(100.0 + i, timestamp=i * 1000))
        assert rt.bar_count == 10

    def test_max_bars_trimming(self) -> None:
        rt = StrategyRuntime(_sma_cross_compiled(), max_bars=5)
        for i in range(20):
            rt.on_kline(_make_kline(100.0 + i, timestamp=i * 1000))
        assert rt.bar_count == 5

    def test_initial_position_is_flat(self) -> None:
        rt = StrategyRuntime(_sma_cross_compiled())
        assert rt.position == "flat"

    def test_sma_cross_generates_buy_signal(self) -> None:
        """Feed a downtrend then an uptrend to trigger SMA cross-above."""
        compiled = _sma_cross_compiled()
        rt = StrategyRuntime(compiled)

        # Phase 1: Downtrend — SMA(5) below SMA(10)
        for i in range(15):
            price = 100.0 - i * 2  # Declining
            rt.on_kline(_make_kline(price, timestamp=i * 3600000))

        assert rt.position == "flat"

        # Phase 2: Sharp uptrend — should cause SMA(5) to cross above SMA(10)
        signals = []
        for i in range(15, 30):
            price = 70.0 + (i - 15) * 5  # Rising fast
            signal = rt.on_kline(_make_kline(price, timestamp=i * 3600000))
            if signal is not None:
                signals.append(signal)

        # Should have generated at least one buy signal
        assert len(signals) >= 1
        assert signals[0].side == OrderSide.BUY
        assert rt.position == "long"

    def test_sma_cross_full_cycle(self) -> None:
        """Test entry and exit: flat → uptrend → buy → downtrend → sell."""
        compiled = _sma_cross_compiled()
        rt = StrategyRuntime(compiled)
        signals = []

        # Phase 1: Flat baseline to establish equal SMAs
        for i in range(12):
            rt.on_kline(_make_kline(100.0, timestamp=i * 3600000))

        # Phase 2: Sharp uptrend — SMA(5) crosses above SMA(10)
        for i in range(12, 25):
            price = 100.0 + (i - 12) * 5
            signal = rt.on_kline(_make_kline(price, timestamp=i * 3600000))
            if signal:
                signals.append(signal)

        # Phase 3: Sharp downtrend — SMA(5) crosses below SMA(10)
        for i in range(25, 45):
            price = 165.0 - (i - 25) * 6
            signal = rt.on_kline(_make_kline(price, timestamp=i * 3600000))
            if signal:
                signals.append(signal)

        # Should have both buy and sell signals
        sides = [s.side for s in signals]
        assert OrderSide.BUY in sides
        assert OrderSide.SELL in sides

    def test_signal_has_correct_fields(self) -> None:
        """Signal should have strategy_id, symbol, and reason."""
        compiled = _sma_cross_compiled()
        rt = StrategyRuntime(compiled)

        # Feed enough data to trigger a signal
        for i in range(30):
            price = 100.0 + i * 3
            signal = rt.on_kline(_make_kline(price, timestamp=i * 3600000))
            if signal is not None:
                assert isinstance(signal, Signal)
                assert signal.strategy_id == "sma-cross-test"
                assert signal.symbol == "BTC/USDT"
                assert signal.reason
                assert signal.timestamp > 0
                return

    def test_reset(self) -> None:
        rt = StrategyRuntime(_sma_cross_compiled())
        for i in range(10):
            rt.on_kline(_make_kline(100.0 + i, timestamp=i * 1000))
        rt.reset()
        assert rt.bar_count == 0
        assert rt.position == "flat"

    def test_rsi_buy_on_oversold(self) -> None:
        """RSI < 30 should trigger a buy signal."""
        compiled = _rsi_compiled()
        rt = StrategyRuntime(compiled)

        # Build up some history with declining prices to push RSI low
        signals = []
        for i in range(30):
            price = 100.0 - i * 2  # Strong downtrend
            signal = rt.on_kline(_make_kline(price, timestamp=i * 3600000))
            if signal:
                signals.append(signal)

        # Should eventually get a buy signal (RSI < 30)
        buy_signals = [s for s in signals if s.side == OrderSide.BUY]
        assert len(buy_signals) >= 1

    def test_no_signal_without_enough_data(self) -> None:
        """With only 1 bar, no signal should be emitted."""
        rt = StrategyRuntime(_sma_cross_compiled())
        signal = rt.on_kline(_make_kline(100.0, timestamp=0))
        assert signal is None
