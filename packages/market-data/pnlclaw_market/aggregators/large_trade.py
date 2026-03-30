"""Large trade detector — filters trades above a notional USD threshold.

Consumes ``TradeEvent`` from the event bus and emits ``LargeTradeEvent``
when a single trade (or aggregate trade) exceeds the configured threshold.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from pnlclaw_types.derivatives import LargeTradeEvent
from pnlclaw_types.market import TradeEvent

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD_USD = 50_000.0
_MAX_HISTORY = 500


class LargeTradeDetector:
    """Detect trades exceeding a configurable notional USD threshold.

    Usage::

        detector = LargeTradeDetector(threshold_usd=100_000)
        detector.on_large_trade(my_callback)
        detector.process(trade_event)  # fires callback if large enough
    """

    def __init__(self, threshold_usd: float = _DEFAULT_THRESHOLD_USD) -> None:
        self._threshold_usd = threshold_usd
        self._callbacks: list[Callable[[LargeTradeEvent], Any]] = []
        self._recent: deque[LargeTradeEvent] = deque(maxlen=_MAX_HISTORY)

    @property
    def threshold_usd(self) -> float:
        return self._threshold_usd

    @threshold_usd.setter
    def threshold_usd(self, value: float) -> None:
        self._threshold_usd = max(0.0, value)

    def on_large_trade(self, callback: Callable[[LargeTradeEvent], Any]) -> None:
        self._callbacks.append(callback)

    def process(self, trade: TradeEvent) -> LargeTradeEvent | None:
        """Evaluate a trade; emit LargeTradeEvent if above threshold."""
        notional = trade.price * trade.quantity
        if notional < self._threshold_usd:
            return None

        event = LargeTradeEvent(
            exchange=trade.exchange,
            symbol=trade.symbol,
            market_type=trade.market_type,
            side=trade.side,
            price=trade.price,
            quantity=trade.quantity,
            notional_usd=notional,
            trade_id=trade.trade_id,
            timestamp=trade.timestamp,
        )
        self._recent.append(event)
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                logger.exception("Error in large trade callback")
        return event

    def get_recent(self, limit: int = 50) -> list[LargeTradeEvent]:
        """Return the most recent large trades."""
        items = list(self._recent)
        return items[-limit:]

    def get_stats(self, window_ms: int = 3_600_000) -> dict[str, Any]:
        """Summary stats for a time window (default 1 hour)."""
        cutoff = int(time.time() * 1000) - window_ms
        buys = [e for e in self._recent if e.timestamp >= cutoff and e.side == "buy"]
        sells = [e for e in self._recent if e.timestamp >= cutoff and e.side == "sell"]
        return {
            "window_ms": window_ms,
            "buy_count": len(buys),
            "sell_count": len(sells),
            "buy_volume_usd": sum(e.notional_usd for e in buys),
            "sell_volume_usd": sum(e.notional_usd for e in sells),
            "total_count": len(buys) + len(sells),
        }
