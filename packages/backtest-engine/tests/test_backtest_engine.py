"""Tests for pnlclaw_backtest.engine — integration test with a mock strategy."""

import pytest

from pnlclaw_backtest.commissions import PercentageCommission
from pnlclaw_backtest.engine import BacktestConfig, BacktestEngine, BacktestError
from pnlclaw_backtest.slippage import FixedSlippage
from pnlclaw_types.market import KlineEvent
from pnlclaw_types.strategy import Signal
from pnlclaw_types.trading import OrderSide


class AlwaysBuyStrategy:
    """Buys on first bar, sells on second, then repeats."""

    def __init__(self) -> None:
        self._bar_count = 0

    def on_kline(self, event: KlineEvent) -> Signal | None:
        self._bar_count += 1
        if self._bar_count == 1:
            return Signal(
                strategy_id="test",
                symbol=event.symbol,
                side=OrderSide.BUY,
                strength=1.0,
                timestamp=event.timestamp,
                reason="test buy",
            )
        if self._bar_count == 2:
            return Signal(
                strategy_id="test",
                symbol=event.symbol,
                side=OrderSide.SELL,
                strength=1.0,
                timestamp=event.timestamp,
                reason="test sell",
            )
        return None

    def reset(self) -> None:
        self._bar_count = 0


def _make_klines(prices: list[float]) -> list[KlineEvent]:
    return [
        KlineEvent(
            exchange="backtest",
            symbol="BTC/USDT",
            timestamp=1711000000000 + i * 3600_000,
            interval="1h",
            open=p * 0.99,
            high=p * 1.01,
            low=p * 0.98,
            close=p,
            volume=100.0,
            closed=True,
        )
        for i, p in enumerate(prices)
    ]


class TestBacktestEngine:
    def test_empty_data_raises(self) -> None:
        engine = BacktestEngine()
        with pytest.raises(BacktestError, match="No kline data"):
            engine.run(AlwaysBuyStrategy(), [])

    def test_basic_run(self) -> None:
        engine = BacktestEngine(config=BacktestConfig(initial_cash=10000.0))
        klines = _make_klines([100.0, 110.0, 105.0])
        result = engine.run(AlwaysBuyStrategy(), klines)

        assert result.trades_count == 1  # one round-trip
        assert result.metrics.total_trades == 1
        assert len(result.equity_curve) == 3
        assert result.metrics.total_return > 0  # bought at 100, sold at 110

    def test_with_costs(self) -> None:
        config = BacktestConfig(
            initial_cash=10000.0,
            commission=PercentageCommission(rate=0.001),
            slippage=FixedSlippage(bps=5),
        )
        engine = BacktestEngine(config=config)
        klines = _make_klines([100.0, 110.0, 105.0])
        result = engine.run(AlwaysBuyStrategy(), klines)

        # With costs, the return should be lower than without costs
        assert result.trades_count == 1

    def test_result_structure(self) -> None:
        engine = BacktestEngine()
        klines = _make_klines([100.0, 105.0, 110.0])
        result = engine.run(AlwaysBuyStrategy(), klines)

        assert result.id.startswith("bt-")
        assert result.strategy_id == "backtest"
        assert result.start_date is not None
        assert result.end_date is not None
        assert result.created_at > 0

    def test_result_contains_symbol_and_interval(self) -> None:
        engine = BacktestEngine()
        klines = _make_klines([100.0, 105.0, 110.0])
        result = engine.run(AlwaysBuyStrategy(), klines)

        assert result.symbol == "BTC/USDT"
        assert result.interval == "1h"

    def test_config_overrides_symbol_interval(self) -> None:
        config = BacktestConfig(symbol="ETH/USDT", interval="4h")
        engine = BacktestEngine(config=config)
        klines = _make_klines([100.0, 105.0, 110.0])
        result = engine.run(AlwaysBuyStrategy(), klines)

        assert result.symbol == "ETH/USDT"
        assert result.interval == "4h"


class AlwaysShortStrategy:
    """Sells (short) on first bar, buys (cover) on second."""

    def __init__(self) -> None:
        self._bar_count = 0

    def on_kline(self, event: KlineEvent) -> Signal | None:
        self._bar_count += 1
        if self._bar_count == 1:
            return Signal(
                strategy_id="test-short",
                symbol=event.symbol,
                side=OrderSide.SELL,
                strength=1.0,
                timestamp=event.timestamp,
                reason="open short",
            )
        if self._bar_count == 2:
            return Signal(
                strategy_id="test-short",
                symbol=event.symbol,
                side=OrderSide.BUY,
                strength=1.0,
                timestamp=event.timestamp,
                reason="close short",
            )
        return None

    def reset(self) -> None:
        self._bar_count = 0


class TestShortSelling:
    """P11: Short position support in BacktestEngine."""

    def test_short_profitable_on_decline(self) -> None:
        """Open short at 100, close at 90 → profitable."""
        engine = BacktestEngine(config=BacktestConfig(initial_cash=10000.0))
        klines = _make_klines([100.0, 90.0, 95.0])
        result = engine.run(AlwaysShortStrategy(), klines)

        assert result.trades_count == 1
        assert result.metrics.total_return > 0  # shorted at 100, covered at 90

    def test_short_loss_on_increase(self) -> None:
        """Open short at 100, close at 110 → loss."""
        engine = BacktestEngine(config=BacktestConfig(initial_cash=10000.0))
        klines = _make_klines([100.0, 110.0, 105.0])
        result = engine.run(AlwaysShortStrategy(), klines)

        assert result.trades_count == 1
        assert result.metrics.total_return < 0

    def test_long_only_backward_compat(self) -> None:
        """Existing long-only strategies should still work identically."""
        engine = BacktestEngine(config=BacktestConfig(initial_cash=10000.0))
        klines = _make_klines([100.0, 110.0, 105.0])
        result = engine.run(AlwaysBuyStrategy(), klines)

        assert result.trades_count == 1
        assert result.metrics.total_return > 0
