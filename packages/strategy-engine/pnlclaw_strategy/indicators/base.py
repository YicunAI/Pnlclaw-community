"""Indicator abstract base class — defines the standard interface for all indicators."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Indicator(ABC):
    """Abstract base class for technical indicators.

    All indicators follow a consistent contract:
    - ``name``: Machine-readable identifier (e.g. ``"sma"``).
    - ``period``: Primary lookback period for the indicator.
    - ``calculate(data)``: Compute indicator values from a price DataFrame.

    Subclasses must implement ``calculate``. The input DataFrame is expected
    to contain at least a ``"close"`` column. Some indicators may use
    ``"high"``, ``"low"``, ``"open"``, or ``"volume"`` columns as well.

    Indicators support chaining: the output Series of one indicator can be
    passed as input to another by adding it as a column to the DataFrame.
    """

    def __init__(self, period: int) -> None:
        if period <= 0:
            raise ValueError(f"Period must be positive, got {period}")
        self._period = period

    @property
    @abstractmethod
    def name(self) -> str:
        """Machine-readable indicator name (e.g. 'sma', 'rsi')."""
        ...

    @property
    def period(self) -> int:
        """Primary lookback period."""
        return self._period

    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """Calculate indicator values from OHLCV data.

        Args:
            data: DataFrame with at least a ``"close"`` column.
                  Index should be monotonically ordered by time.

        Returns:
            Series of indicator values, aligned with the input index.
            Early values where the lookback is insufficient will be NaN.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(period={self._period})"
