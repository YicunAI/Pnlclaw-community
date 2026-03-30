"""Bollinger Bands indicator."""

from __future__ import annotations

import pandas as pd

from pnlclaw_strategy.indicators.base import Indicator


class BollingerBandsResult:
    """Container for Bollinger Bands calculation results."""

    __slots__ = ("upper", "middle", "lower")

    def __init__(self, upper: pd.Series, middle: pd.Series, lower: pd.Series) -> None:
        self.upper = upper
        self.middle = middle
        self.lower = lower


class BollingerBands(Indicator):
    """Bollinger Bands (upper, middle, lower).

    Default: 20-period SMA with 2 standard deviations.
    """

    def __init__(self, period: int = 20, num_std: float = 2.0) -> None:
        super().__init__(period)
        self._num_std = num_std

    @property
    def name(self) -> str:
        return "bbands"

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """Return the middle band (SMA)."""
        return data["close"].rolling(window=self._period, min_periods=self._period).mean()

    def calculate_full(self, data: pd.DataFrame) -> BollingerBandsResult:
        """Calculate all three Bollinger Bands."""
        close = data["close"]
        middle = close.rolling(window=self._period, min_periods=self._period).mean()
        std = close.rolling(window=self._period, min_periods=self._period).std()
        upper = middle + self._num_std * std
        lower = middle - self._num_std * std
        return BollingerBandsResult(upper=upper, middle=middle, lower=lower)

    def __repr__(self) -> str:
        return f"BollingerBands(period={self._period}, std={self._num_std})"
