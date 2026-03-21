"""Tests for pnlclaw_market.state_engine — market state classification."""

from __future__ import annotations

import pandas as pd
import pytest

from pnlclaw_types.agent import MarketRegime, MarketState
from pnlclaw_types.market import KlineEvent

from pnlclaw_market.state_engine import (
    InsufficientDataError,
    MarketStateEngine,
    classify_regime,
    classify_trend_strength,
    classify_volatility,
    compute_atr,
    compute_adx_proxy,
    compute_momentum,
    klines_to_dataframe,
)


def _make_klines(n: int = 30, base_price: float = 67000.0) -> list[KlineEvent]:
    """Generate synthetic kline data with a slight uptrend."""
    klines = []
    for i in range(n):
        price = base_price + i * 50.0  # uptrend
        klines.append(
            KlineEvent(
                exchange="binance",
                symbol="BTC/USDT",
                timestamp=1711000000000 + i * 3600000,
                interval="1h",
                open=price - 10,
                high=price + 100,
                low=price - 100,
                close=price,
                volume=1000.0 + i * 10,
                closed=True,
            )
        )
    return klines


def _make_ranging_klines(n: int = 30, base_price: float = 67000.0) -> list[KlineEvent]:
    """Generate synthetic kline data with sideways movement."""
    klines = []
    for i in range(n):
        # Oscillate around base price
        offset = 50.0 if i % 2 == 0 else -50.0
        price = base_price + offset
        klines.append(
            KlineEvent(
                exchange="binance",
                symbol="BTC/USDT",
                timestamp=1711000000000 + i * 3600000,
                interval="1h",
                open=price - 5,
                high=price + 20,
                low=price - 20,
                close=price,
                volume=1000.0,
                closed=True,
            )
        )
    return klines


class TestKlinesToDataframe:
    def test_basic_conversion(self) -> None:
        klines = _make_klines(5)
        df = klines_to_dataframe(klines)
        assert len(df) == 5
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]

    def test_empty_raises(self) -> None:
        with pytest.raises(InsufficientDataError):
            klines_to_dataframe([])

    def test_sorted_by_timestamp(self) -> None:
        klines = _make_klines(5)
        reversed_klines = list(reversed(klines))
        df = klines_to_dataframe(reversed_klines)
        assert df["timestamp"].is_monotonic_increasing


class TestIndicators:
    def test_compute_atr(self) -> None:
        df = klines_to_dataframe(_make_klines(30))
        atr = compute_atr(df)
        assert len(atr) == 30
        assert all(atr >= 0)

    def test_compute_adx_proxy(self) -> None:
        df = klines_to_dataframe(_make_klines(30))
        adx = compute_adx_proxy(df)
        assert len(adx) == 30
        assert all(adx >= 0)

    def test_compute_momentum(self) -> None:
        df = klines_to_dataframe(_make_klines(30))
        mom = compute_momentum(df)
        assert len(mom) == 30


class TestClassifiers:
    def test_classify_regime_trending(self) -> None:
        assert classify_regime(30.0, 5.0) == MarketRegime.TRENDING

    def test_classify_regime_ranging(self) -> None:
        assert classify_regime(10.0, 0.0) == MarketRegime.RANGING

    def test_classify_regime_volatile(self) -> None:
        # ADX between ranging and trending thresholds
        assert classify_regime(20.0, 0.0) == MarketRegime.VOLATILE

    def test_classify_trend_strength(self) -> None:
        assert classify_trend_strength(0.0) == 0.0
        assert classify_trend_strength(50.0) == 0.5
        assert classify_trend_strength(100.0) == 1.0
        assert classify_trend_strength(150.0) == 1.0  # clamped

    def test_classify_volatility(self) -> None:
        assert classify_volatility(0.0) == 0.0
        assert 0.0 < classify_volatility(0.01) < 0.5
        assert classify_volatility(0.05) == 1.0  # at HIGH threshold
        assert classify_volatility(0.1) == 1.0   # clamped


class TestMarketStateEngine:
    def test_analyze_trending(self) -> None:
        engine = MarketStateEngine()
        klines = _make_klines(30)
        state = engine.analyze("BTC/USDT", klines)
        assert isinstance(state, MarketState)
        assert state.symbol == "BTC/USDT"
        assert 0.0 <= state.trend_strength <= 1.0
        assert 0.0 <= state.volatility <= 1.0
        assert state.regime in list(MarketRegime)

    def test_analyze_with_dataframe(self) -> None:
        engine = MarketStateEngine()
        df = klines_to_dataframe(_make_klines(30))
        state = engine.analyze("BTC/USDT", df)
        assert isinstance(state, MarketState)

    def test_insufficient_data_raises(self) -> None:
        engine = MarketStateEngine()
        with pytest.raises(InsufficientDataError):
            engine.analyze("BTC/USDT", _make_klines(5))

    def test_ranging_market(self) -> None:
        engine = MarketStateEngine()
        klines = _make_ranging_klines(30)
        state = engine.analyze("BTC/USDT", klines)
        assert isinstance(state, MarketState)
        # Ranging market should have lower trend strength
        assert state.trend_strength < 0.8

    def test_timestamp_is_set(self) -> None:
        engine = MarketStateEngine()
        state = engine.analyze("BTC/USDT", _make_klines(30))
        assert state.timestamp > 0
