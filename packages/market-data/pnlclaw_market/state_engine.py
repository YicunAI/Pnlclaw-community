"""Market state classification engine (v0.1 simplified).

Computes MarketState (regime, trend_strength, volatility) from kline data
using a small set of core indicators: ADX-proxy, ATR, and simple momentum.

This is the v0.1 simplified version: single timeframe, 3-5 core indicators.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

import numpy as np
import pandas as pd

from pnlclaw_types.agent import MarketRegime, MarketState
from pnlclaw_types.market import KlineEvent

# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------

_ADX_PERIOD = 14
_ATR_PERIOD = 14
_MOMENTUM_PERIOD = 10

# Regime thresholds
_ADX_TRENDING_THRESHOLD = 25.0  # ADX above this → trending
_ADX_STRONG_THRESHOLD = 40.0    # ADX above this → strong trend

# Volatility thresholds (ATR as % of price)
_VOL_LOW = 0.01       # < 1% → low
_VOL_NORMAL = 0.025   # < 2.5% → normal
_VOL_HIGH = 0.05      # < 5% → high, else extreme


class InsufficientDataError(Exception):
    """Raised when there is not enough kline data for analysis."""


def klines_to_dataframe(klines: Sequence[KlineEvent]) -> pd.DataFrame:
    """Convert a sequence of KlineEvent to a pandas DataFrame.

    Returns a DataFrame with columns: open, high, low, close, volume,
    indexed by timestamp, sorted ascending.
    """
    if not klines:
        raise InsufficientDataError("No kline data provided")

    records = [
        {
            "timestamp": k.timestamp,
            "open": k.open,
            "high": k.high,
            "low": k.low,
            "close": k.close,
            "volume": k.volume,
        }
        for k in klines
    ]
    df = pd.DataFrame(records)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def compute_atr(df: pd.DataFrame, period: int = _ATR_PERIOD) -> pd.Series:
    """Compute Average True Range (ATR).

    Args:
        df: DataFrame with 'high', 'low', 'close' columns.
        period: Lookback period.

    Returns:
        Series of ATR values.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.rolling(window=period, min_periods=1).mean()


def compute_adx_proxy(df: pd.DataFrame, period: int = _ADX_PERIOD) -> pd.Series:
    """Compute a simplified ADX proxy (directional movement strength).

    This is a v0.1 simplified version that uses smoothed directional
    movement ratio as a trend strength indicator, without computing
    the full Wilder's ADX.

    Args:
        df: DataFrame with 'high', 'low', 'close' columns.
        period: Lookback period.

    Returns:
        Series of ADX-proxy values (0-100 scale).
    """
    high = df["high"]
    low = df["low"]

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )

    atr = compute_atr(df, period)

    # Smoothed DI+ and DI-
    smooth_plus = plus_dm.rolling(window=period, min_periods=1).mean()
    smooth_minus = minus_dm.rolling(window=period, min_periods=1).mean()

    di_plus = 100.0 * smooth_plus / atr.replace(0, np.nan)
    di_minus = 100.0 * smooth_minus / atr.replace(0, np.nan)

    di_sum = di_plus + di_minus
    di_diff = (di_plus - di_minus).abs()

    dx = 100.0 * di_diff / di_sum.replace(0, np.nan)
    adx = dx.rolling(window=period, min_periods=1).mean()

    return adx.fillna(0.0)


def compute_momentum(df: pd.DataFrame, period: int = _MOMENTUM_PERIOD) -> pd.Series:
    """Compute price momentum as percentage change over *period* bars.

    Args:
        df: DataFrame with 'close' column.
        period: Lookback period.

    Returns:
        Series of momentum values (percentage).
    """
    close = df["close"]
    return close.pct_change(periods=period).fillna(0.0) * 100.0


def classify_regime(adx: float, momentum: float) -> MarketRegime:
    """Classify the market regime based on ADX and momentum.

    Args:
        adx: Current ADX proxy value (0-100).
        momentum: Current momentum value (percentage).

    Returns:
        MarketRegime enum value.
    """
    if adx >= _ADX_TRENDING_THRESHOLD:
        return MarketRegime.TRENDING
    elif adx < _ADX_TRENDING_THRESHOLD * 0.6:
        return MarketRegime.RANGING
    else:
        return MarketRegime.VOLATILE


def classify_trend_strength(adx: float) -> float:
    """Convert ADX proxy value to a 0.0-1.0 trend strength score.

    Args:
        adx: Current ADX proxy value (0-100).

    Returns:
        Normalized trend strength (0.0 = no trend, 1.0 = very strong).
    """
    return min(max(adx / 100.0, 0.0), 1.0)


def classify_volatility(atr_pct: float) -> float:
    """Convert ATR percentage to a normalized volatility score.

    The score maps to qualitative levels:
        - < 1%   → low      (score ~0.1-0.2)
        - < 2.5% → normal   (score ~0.3-0.5)
        - < 5%   → high     (score ~0.6-0.8)
        - >= 5%  → extreme  (score ~0.8-1.0)

    Args:
        atr_pct: ATR as a percentage of price (0.01 = 1%).

    Returns:
        Normalized volatility score (0.0-1.0).
    """
    if atr_pct <= 0:
        return 0.0
    # Map to 0-1 using a sigmoid-like curve
    # 5% ATR → ~0.8, 10% → ~0.95
    score = min(atr_pct / _VOL_HIGH, 1.0)
    return round(score, 4)


class MarketStateEngine:
    """Market state classification engine (v0.1 simplified).

    Analyzes kline data to produce a ``MarketState`` describing the
    current market regime, trend strength, and volatility level.

    Single timeframe, uses ADX-proxy + ATR + momentum as core indicators.

    Args:
        adx_period: ADX indicator period.
        atr_period: ATR indicator period.
        momentum_period: Momentum lookback period.
    """

    def __init__(
        self,
        *,
        adx_period: int = _ADX_PERIOD,
        atr_period: int = _ATR_PERIOD,
        momentum_period: int = _MOMENTUM_PERIOD,
    ) -> None:
        self._adx_period = adx_period
        self._atr_period = atr_period
        self._momentum_period = momentum_period

    def analyze(
        self,
        symbol: str,
        klines: Sequence[KlineEvent] | pd.DataFrame,
    ) -> MarketState:
        """Analyze kline data and return a MarketState classification.

        Args:
            symbol: Normalized trading pair, e.g. ``"BTC/USDT"``.
            klines: Kline data as a list of KlineEvent or a DataFrame
                    with columns: open, high, low, close, volume.

        Returns:
            MarketState with regime, trend_strength, and volatility.

        Raises:
            InsufficientDataError: If fewer than ``max(adx_period, atr_period) + 1``
                bars are provided.
        """
        if isinstance(klines, pd.DataFrame):
            df = klines.copy()
        else:
            df = klines_to_dataframe(klines)

        min_bars = max(self._adx_period, self._atr_period, self._momentum_period) + 1
        if len(df) < min_bars:
            raise InsufficientDataError(
                f"Need at least {min_bars} bars, got {len(df)}"
            )

        # Compute indicators
        adx_series = compute_adx_proxy(df, self._adx_period)
        atr_series = compute_atr(df, self._atr_period)
        momentum_series = compute_momentum(df, self._momentum_period)

        # Take latest values
        adx_val = float(adx_series.iloc[-1])
        atr_val = float(atr_series.iloc[-1])
        momentum_val = float(momentum_series.iloc[-1])
        last_close = float(df["close"].iloc[-1])

        # ATR as percentage of price
        atr_pct = atr_val / last_close if last_close > 0 else 0.0

        # Classify
        regime = classify_regime(adx_val, momentum_val)
        trend_strength = classify_trend_strength(adx_val)
        volatility = classify_volatility(atr_pct)

        return MarketState(
            symbol=symbol,
            regime=regime,
            trend_strength=round(trend_strength, 4),
            volatility=round(volatility, 4),
            timestamp=int(time.time() * 1000),
        )
