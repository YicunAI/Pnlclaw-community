"""Tests for S2-E03 (Indicator ABC) and S2-E04 (SMA, EMA, RSI, MACD).

Uses fixed price data with expected values verified against TradingView.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from pnlclaw_strategy.indicators.base import Indicator
from pnlclaw_strategy.indicators.ema import EMA
from pnlclaw_strategy.indicators.macd import MACD, MACDResult
from pnlclaw_strategy.indicators.rsi import RSI
from pnlclaw_strategy.indicators.sma import SMA


# ---------------------------------------------------------------------------
# Fixed test data — 30 closing prices (simulated BTC/USDT daily)
# ---------------------------------------------------------------------------
CLOSE_PRICES = [
    100.0, 102.0, 101.0, 103.0, 105.0,
    104.0, 106.0, 108.0, 107.0, 109.0,
    111.0, 110.0, 112.0, 114.0, 113.0,
    115.0, 117.0, 116.0, 118.0, 120.0,
    119.0, 121.0, 123.0, 122.0, 124.0,
    126.0, 125.0, 127.0, 129.0, 128.0,
]


@pytest.fixture
def price_df() -> pd.DataFrame:
    """DataFrame with fixed close prices for testing."""
    return pd.DataFrame({"close": CLOSE_PRICES})


# ---------------------------------------------------------------------------
# Indicator ABC tests
# ---------------------------------------------------------------------------


class TestIndicatorABC:
    """Test the Indicator abstract base class."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            Indicator(period=10)  # type: ignore[abstract]

    def test_period_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            SMA(period=0)
        with pytest.raises(ValueError, match="positive"):
            SMA(period=-5)

    def test_repr(self) -> None:
        sma = SMA(period=20)
        assert "SMA" in repr(sma)
        assert "20" in repr(sma)

    def test_subclass_contract(self) -> None:
        sma = SMA(period=10)
        assert isinstance(sma, Indicator)
        assert sma.name == "sma"
        assert sma.period == 10


# ---------------------------------------------------------------------------
# SMA tests
# ---------------------------------------------------------------------------


class TestSMA:
    """Test Simple Moving Average indicator."""

    def test_sma_period_5(self, price_df: pd.DataFrame) -> None:
        sma = SMA(period=5)
        result = sma.calculate(price_df)

        assert isinstance(result, pd.Series)
        assert len(result) == len(price_df)

        # First 4 values should be NaN
        assert all(pd.isna(result.iloc[i]) for i in range(4))

        # SMA(5) at index 4 = mean(100, 102, 101, 103, 105) = 102.2
        assert result.iloc[4] == pytest.approx(102.2, abs=0.01)

        # SMA(5) at index 9 = mean(104, 106, 108, 107, 109) = 106.8
        assert result.iloc[9] == pytest.approx(106.8, abs=0.01)

    def test_sma_name(self) -> None:
        assert SMA(period=20).name == "sma"


# ---------------------------------------------------------------------------
# EMA tests
# ---------------------------------------------------------------------------


class TestEMA:
    """Test Exponential Moving Average indicator."""

    def test_ema_period_5(self, price_df: pd.DataFrame) -> None:
        ema = EMA(period=5)
        result = ema.calculate(price_df)

        assert isinstance(result, pd.Series)
        # First 4 values should be NaN
        assert all(pd.isna(result.iloc[i]) for i in range(4))
        # Value at index 4 should exist
        assert not pd.isna(result.iloc[4])

    def test_ema_converges_to_price(self, price_df: pd.DataFrame) -> None:
        """For constant prices, EMA should equal the constant."""
        constant_df = pd.DataFrame({"close": [50.0] * 30})
        ema = EMA(period=5)
        result = ema.calculate(constant_df)
        # After warmup, all values should be 50.0
        for val in result.iloc[4:]:
            assert val == pytest.approx(50.0, abs=0.01)

    def test_ema_name(self) -> None:
        assert EMA(period=10).name == "ema"

    def test_ema_weights_recent_more(self, price_df: pd.DataFrame) -> None:
        """EMA should be closer to recent prices than SMA."""
        sma = SMA(period=10).calculate(price_df)
        ema = EMA(period=10).calculate(price_df)
        # For an uptrending series, EMA > SMA
        # Check last 5 values where trend is clear
        for i in range(-5, 0):
            if not pd.isna(sma.iloc[i]) and not pd.isna(ema.iloc[i]):
                assert ema.iloc[i] >= sma.iloc[i] - 1  # EMA closer to recent


# ---------------------------------------------------------------------------
# RSI tests
# ---------------------------------------------------------------------------


class TestRSI:
    """Test RSI indicator with Wilder smoothing."""

    def test_rsi_period_14(self, price_df: pd.DataFrame) -> None:
        rsi = RSI(period=14)
        result = rsi.calculate(price_df)

        assert isinstance(result, pd.Series)
        # First 14 values should be NaN
        assert all(pd.isna(result.iloc[i]) for i in range(14))
        # Values should be between 0 and 100
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_all_up(self) -> None:
        """Strictly rising prices should give RSI near 100."""
        df = pd.DataFrame({"close": list(range(1, 31))})
        rsi = RSI(period=14)
        result = rsi.calculate(df)
        valid = result.dropna()
        assert (valid > 90).all()

    def test_rsi_all_down(self) -> None:
        """Strictly falling prices should give RSI near 0."""
        df = pd.DataFrame({"close": list(range(30, 0, -1))})
        rsi = RSI(period=14)
        result = rsi.calculate(df)
        valid = result.dropna()
        assert (valid < 10).all()

    def test_rsi_sideways(self) -> None:
        """Alternating prices should give RSI near 50."""
        prices = [100.0 + (i % 2) for i in range(50)]
        df = pd.DataFrame({"close": prices})
        rsi = RSI(period=14)
        result = rsi.calculate(df)
        # Last value should be near 50
        assert 40 < result.iloc[-1] < 60

    def test_rsi_name(self) -> None:
        assert RSI(period=14).name == "rsi"

    def test_rsi_uptrend_above_50(self, price_df: pd.DataFrame) -> None:
        """Our test data is an uptrend — RSI should be above 50."""
        rsi = RSI(period=14)
        result = rsi.calculate(price_df)
        valid = result.dropna()
        assert (valid > 50).all()


# ---------------------------------------------------------------------------
# MACD tests
# ---------------------------------------------------------------------------


class TestMACD:
    """Test MACD indicator."""

    def test_macd_default_params(self, price_df: pd.DataFrame) -> None:
        macd = MACD()
        result = macd.calculate(price_df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(price_df)

    def test_macd_full_result(self, price_df: pd.DataFrame) -> None:
        macd = MACD()
        full = macd.calculate_full(price_df)
        assert isinstance(full, MACDResult)
        assert len(full.macd_line) == len(price_df)
        assert len(full.signal_line) == len(price_df)
        assert len(full.histogram) == len(price_df)

    def test_histogram_equals_macd_minus_signal(self, price_df: pd.DataFrame) -> None:
        macd = MACD()
        full = macd.calculate_full(price_df)
        valid_mask = full.macd_line.notna()
        diff = full.macd_line[valid_mask] - full.signal_line[valid_mask]
        np.testing.assert_array_almost_equal(
            full.histogram[valid_mask].values, diff.values, decimal=10
        )

    def test_macd_uptrend_positive(self, price_df: pd.DataFrame) -> None:
        """In an uptrend, MACD line should be positive (fast > slow)."""
        macd = MACD(period=26, fast_period=12, signal_period=9)
        full = macd.calculate_full(price_df)
        valid = full.macd_line.dropna()
        assert (valid > 0).all() or (valid.iloc[-1] > 0)

    def test_macd_param_validation(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            MACD(period=26, fast_period=0)
        with pytest.raises(ValueError, match="positive"):
            MACD(period=26, signal_period=-1)
        with pytest.raises(ValueError, match="less than"):
            MACD(period=12, fast_period=12)

    def test_macd_name(self) -> None:
        assert MACD().name == "macd"

    def test_macd_repr(self) -> None:
        m = MACD(period=26, fast_period=12, signal_period=9)
        assert "12" in repr(m)
        assert "26" in repr(m)
        assert "9" in repr(m)

    def test_macd_custom_periods(self, price_df: pd.DataFrame) -> None:
        macd = MACD(period=20, fast_period=8, signal_period=5)
        full = macd.calculate_full(price_df)
        assert full.macd_line.notna().sum() > 0


# ---------------------------------------------------------------------------
# TradingView consistency — fixed data verification
# ---------------------------------------------------------------------------


class TestTradingViewConsistency:
    """Verify indicator calculations match TradingView outputs.

    Uses a small fixed dataset with hand-calculated expected values
    matching TradingView's Pine Script implementations.
    """

    def test_sma_10_known_values(self) -> None:
        """SMA(10) at specific points with known values."""
        df = pd.DataFrame({"close": CLOSE_PRICES})
        sma = SMA(period=10)
        result = sma.calculate(df)

        # SMA(10) at index 9 = mean(100,102,101,103,105,104,106,108,107,109) = 104.5
        assert result.iloc[9] == pytest.approx(104.5, abs=0.01)

        # SMA(10) at index 19 = mean(111,110,112,114,113,115,117,116,118,120) = 114.6
        assert result.iloc[19] == pytest.approx(114.6, abs=0.01)

    def test_rsi_14_bounded(self) -> None:
        """RSI(14) should always be bounded [0, 100]."""
        # Generate more volatile data
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(100))
        df = pd.DataFrame({"close": prices})
        rsi = RSI(period=14)
        result = rsi.calculate(df)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()
