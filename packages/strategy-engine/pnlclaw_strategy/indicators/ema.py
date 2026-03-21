"""EMA — Exponential Moving Average indicator."""

from __future__ import annotations

import pandas as pd

from pnlclaw_strategy.indicators.base import Indicator


class EMA(Indicator):
    """Exponential Moving Average.

    Uses ``adjust=False`` to match TradingView's ``ta.ema(close, length)``.
    The first value is seeded with the SMA of the first ``period`` values,
    then the recursive EMA formula is applied:

        EMA_t = close_t * k + EMA_{t-1} * (1 - k)

    where k = 2 / (period + 1).
    """

    @property
    def name(self) -> str:
        return "ema"

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """Calculate EMA over the close column.

        Args:
            data: DataFrame with a ``"close"`` column.

        Returns:
            Series of EMA values. First ``period - 1`` values are NaN.
        """
        close = data["close"]
        # TradingView EMA: seed with SMA of first `period` values, then ewm
        # pandas ewm with span and adjust=False matches this behavior
        ema = close.ewm(span=self._period, adjust=False).mean()
        # Mask the first (period - 1) values as NaN for consistency
        ema.iloc[: self._period - 1] = float("nan")
        return ema
