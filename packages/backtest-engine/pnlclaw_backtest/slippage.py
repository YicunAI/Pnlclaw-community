"""Slippage models for backtesting.

All slippage models implement the ``SlippageModel`` Protocol so they can
be injected into ``SimulatedBroker`` and ``BacktestConfig``.
"""

from __future__ import annotations

from typing import Protocol

from pnlclaw_types.trading import OrderSide


class SlippageModel(Protocol):
    """Unified slippage interface.

    ``apply`` adjusts the raw price to simulate market impact / slippage.
    """

    def apply(self, price: float, side: OrderSide) -> float:
        """Return the price after applying slippage.

        Args:
            price: Raw execution price.
            side: Order direction (buys slip up, sells slip down).
        """
        ...


class NoSlippage:
    """Zero slippage — fills at the exact price."""

    def apply(self, price: float, side: OrderSide) -> float:
        return price


class FixedSlippage:
    """Fixed slippage in basis points.

    1 basis point = 0.01%.  Default is 1 bp.

    For a BUY, the fill price is *higher* than the reference price.
    For a SELL, the fill price is *lower*.

    Args:
        bps: Slippage in basis points (default 1).
    """

    def __init__(self, bps: float = 1.0) -> None:
        if bps < 0:
            raise ValueError("Slippage basis points must be non-negative.")
        self._fraction = bps / 10_000.0

    def apply(self, price: float, side: OrderSide) -> float:
        if side == OrderSide.BUY:
            return price * (1.0 + self._fraction)
        return price * (1.0 - self._fraction)
