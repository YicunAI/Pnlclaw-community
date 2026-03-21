"""Protocol interfaces for backtest-engine.

backtest-engine depends on strategy-engine at runtime, but uses Protocol
to decouple at the package level so the two can be developed in parallel.
"""

from __future__ import annotations

from typing import Protocol

from pnlclaw_types.market import KlineEvent
from pnlclaw_types.strategy import Signal


class StrategyRunner(Protocol):
    """Strategy runtime interface.

    backtest-engine only depends on this Protocol, not on
    ``pnlclaw_strategy`` implementation.  Any object that implements
    ``on_kline`` and ``reset`` satisfies this contract.
    """

    def on_kline(self, event: KlineEvent) -> Signal | None:
        """Process a single kline and optionally emit a trading signal.

        Args:
            event: A finalized (closed) kline bar.

        Returns:
            A Signal if the strategy wants to trade, or None to hold.
        """
        ...

    def reset(self) -> None:
        """Reset internal state for a fresh backtest run."""
        ...
