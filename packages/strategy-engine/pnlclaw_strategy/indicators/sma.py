"""SMA — Simple Moving Average indicator."""

from __future__ import annotations

import pandas as pd

from pnlclaw_strategy.indicators.base import Indicator


class SMA(Indicator):
    """Simple Moving Average.

    Calculates the arithmetic mean of the closing price over the last
    ``period`` bars. Matches TradingView's ``ta.sma(close, length)``.
    """

    @property
    def name(self) -> str:
        return "sma"

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """Calculate SMA over the close column.

        Args:
            data: DataFrame with a ``"close"`` column.

        Returns:
            Series of SMA values. First ``period - 1`` values are NaN.
        """
        return data["close"].rolling(window=self._period, min_periods=self._period).mean()
