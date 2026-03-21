"""Commission models for backtesting.

All commission models implement the ``CommissionModel`` Protocol so they
can be injected into ``SimulatedBroker`` and ``BacktestConfig``.
"""

from __future__ import annotations

from typing import Protocol


class CommissionModel(Protocol):
    """Unified commission interface."""

    def calculate(self, price: float, quantity: float) -> float:
        """Return the fee for a fill at *price* for *quantity*.

        Args:
            price: Fill price.
            quantity: Fill quantity.

        Returns:
            Fee amount in quote currency.
        """
        ...


class NoCommission:
    """Zero commission."""

    def calculate(self, price: float, quantity: float) -> float:
        return 0.0


class PercentageCommission:
    """Percentage-based commission.

    Default rate is 0.1 % (10 bps), typical for crypto spot trading.

    Args:
        rate: Commission rate as a decimal (0.001 = 0.1%).
    """

    def __init__(self, rate: float = 0.001) -> None:
        if rate < 0:
            raise ValueError("Commission rate must be non-negative.")
        self._rate = rate

    def calculate(self, price: float, quantity: float) -> float:
        return price * quantity * self._rate
