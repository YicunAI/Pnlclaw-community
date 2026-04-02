"""MACD — Moving Average Convergence Divergence indicator."""

from __future__ import annotations

import pandas as pd

from pnlclaw_strategy.indicators.base import Indicator


class MACDResult:
    """Container for MACD calculation results.

    Attributes:
        macd_line: MACD line (fast EMA - slow EMA).
        signal_line: Signal line (EMA of MACD line).
        histogram: MACD histogram (macd_line - signal_line).
    """

    __slots__ = ("macd_line", "signal_line", "histogram")

    def __init__(self, macd_line: pd.Series, signal_line: pd.Series, histogram: pd.Series) -> None:
        self.macd_line = macd_line
        self.signal_line = signal_line
        self.histogram = histogram


class MACD(Indicator):
    """MACD (Moving Average Convergence Divergence).

    Matches TradingView's ``ta.macd(close, fastlen, slowlen, siglen)``.

    Default parameters: fast=12, slow=26, signal=9.
    The ``period`` parameter controls the slow EMA period.
    """

    def __init__(
        self,
        period: int = 26,
        fast_period: int = 12,
        signal_period: int = 9,
    ) -> None:
        super().__init__(period)
        if fast_period <= 0:
            raise ValueError(f"fast_period must be positive, got {fast_period}")
        if signal_period <= 0:
            raise ValueError(f"signal_period must be positive, got {signal_period}")
        if fast_period >= period:
            raise ValueError(f"fast_period ({fast_period}) must be less than slow period ({period})")
        self._fast_period = fast_period
        self._signal_period = signal_period

    @property
    def name(self) -> str:
        return "macd"

    @property
    def fast_period(self) -> int:
        """Fast EMA period."""
        return self._fast_period

    @property
    def signal_period(self) -> int:
        """Signal line EMA period."""
        return self._signal_period

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """Calculate MACD line (fast EMA - slow EMA).

        For the full MACD result including signal and histogram,
        use ``calculate_full()``.

        Args:
            data: DataFrame with a ``"close"`` column.

        Returns:
            Series of MACD line values.
        """
        result = self.calculate_full(data)
        return result.macd_line

    def calculate_full(self, data: pd.DataFrame) -> MACDResult:
        """Calculate all MACD components: MACD line, signal line, histogram.

        Args:
            data: DataFrame with a ``"close"`` column.

        Returns:
            MACDResult with macd_line, signal_line, and histogram.
        """
        close = data["close"]

        fast_ema = close.ewm(span=self._fast_period, adjust=False).mean()
        slow_ema = close.ewm(span=self._period, adjust=False).mean()

        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=self._signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        # Mask early values where slow EMA hasn't converged
        mask_len = self._period - 1
        macd_line.iloc[:mask_len] = float("nan")
        signal_line.iloc[:mask_len] = float("nan")
        histogram.iloc[:mask_len] = float("nan")

        return MACDResult(
            macd_line=macd_line,
            signal_line=signal_line,
            histogram=histogram,
        )

    def __repr__(self) -> str:
        return f"MACD(fast={self._fast_period}, slow={self._period}, signal={self._signal_period})"
