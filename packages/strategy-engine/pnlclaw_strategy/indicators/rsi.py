"""RSI — Relative Strength Index indicator (Wilder smoothing)."""

from __future__ import annotations

import pandas as pd

from pnlclaw_strategy.indicators.base import Indicator


class RSI(Indicator):
    """Relative Strength Index using Wilder's smoothing method.

    Matches TradingView's ``ta.rsi(close, length)``:
    1. Calculate price changes (delta).
    2. Separate gains and losses.
    3. Apply Wilder smoothing (EMA with alpha = 1/period).
    4. RS = avg_gain / avg_loss; RSI = 100 - 100 / (1 + RS).
    """

    @property
    def name(self) -> str:
        return "rsi"

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """Calculate RSI over the close column.

        Args:
            data: DataFrame with a ``"close"`` column.

        Returns:
            Series of RSI values (0-100). First ``period`` values are NaN.
        """
        close = data["close"]
        delta = close.diff()

        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        # Wilder smoothing: EMA with alpha = 1/period (equivalent to com=period-1)
        avg_gain = gain.ewm(alpha=1.0 / self._period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / self._period, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # Mask the first `period` values as NaN (insufficient lookback)
        rsi.iloc[: self._period] = float("nan")

        return rsi
