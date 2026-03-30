"""Large order detector — scans order book snapshots for whale-sized resting orders.

Compares consecutive snapshots to detect large order appearances/disappearances.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from pnlclaw_types.derivatives import LargeOrderEvent
from pnlclaw_types.market import OrderBookL2Snapshot, PriceLevel

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD_USD = 100_000.0
_MAX_HISTORY = 200


class LargeOrderDetector:
    """Detect single-price-level orders exceeding a notional USD threshold.

    Usage::

        detector = LargeOrderDetector(threshold_usd=200_000)
        detector.on_large_order(my_callback)
        detector.process(orderbook_snapshot)
    """

    def __init__(self, threshold_usd: float = _DEFAULT_THRESHOLD_USD) -> None:
        self._threshold_usd = threshold_usd
        self._callbacks: list[Callable[[LargeOrderEvent], Any]] = []
        self._recent: deque[LargeOrderEvent] = deque(maxlen=_MAX_HISTORY)
        self._prev_large: dict[str, dict[str, float]] = {}

    @property
    def threshold_usd(self) -> float:
        return self._threshold_usd

    @threshold_usd.setter
    def threshold_usd(self, value: float) -> None:
        self._threshold_usd = max(0.0, value)

    def on_large_order(self, callback: Callable[[LargeOrderEvent], Any]) -> None:
        self._callbacks.append(callback)

    def process(self, snapshot: OrderBookL2Snapshot) -> list[LargeOrderEvent]:
        """Scan a snapshot and emit events for large resting orders."""
        now_ms = int(time.time() * 1000)
        symbol = snapshot.symbol
        events: list[LargeOrderEvent] = []

        current_large: dict[str, float] = {}

        for rank, level in enumerate(snapshot.bids):
            ev = self._check_level(level, "bid", rank, snapshot, now_ms, current_large)
            if ev:
                events.append(ev)

        for rank, level in enumerate(snapshot.asks):
            ev = self._check_level(level, "ask", rank, snapshot, now_ms, current_large)
            if ev:
                events.append(ev)

        # Detect disappeared large orders
        prev = self._prev_large.get(symbol, {})
        for key, prev_notional in prev.items():
            if key not in current_large:
                side_str, price_str = key.split(":", 1)
                price = float(price_str)
                prev_qty = prev_notional / price if price > 0 else 1.0
                events.append(LargeOrderEvent(
                    exchange=snapshot.exchange,
                    symbol=symbol,
                    market_type=snapshot.market_type,
                    side=side_str,  # type: ignore[arg-type]
                    price=price,
                    quantity=prev_qty,
                    notional_usd=prev_notional,
                    depth_rank=0,
                    event_type="disappeared",
                    timestamp=now_ms,
                ))

        self._prev_large[symbol] = current_large

        for ev in events:
            self._recent.append(ev)
            for cb in self._callbacks:
                try:
                    cb(ev)
                except Exception:
                    logger.exception("Error in large order callback")

        return events

    def _check_level(
        self,
        level: PriceLevel,
        side: str,
        rank: int,
        snapshot: OrderBookL2Snapshot,
        now_ms: int,
        current_large: dict[str, float],
    ) -> LargeOrderEvent | None:
        notional = level.price * level.quantity
        if notional < self._threshold_usd:
            return None

        key = f"{side}:{level.price}"
        current_large[key] = notional
        prev = self._prev_large.get(snapshot.symbol, {})

        if key not in prev:
            event_type = "appeared"
        elif notional > prev[key] * 1.1:
            event_type = "increased"
        elif notional < prev[key] * 0.9:
            event_type = "decreased"
        else:
            return None

        return LargeOrderEvent(
            exchange=snapshot.exchange,
            symbol=snapshot.symbol,
            market_type=snapshot.market_type,
            side=side,  # type: ignore[arg-type]
            price=level.price,
            quantity=level.quantity,
            notional_usd=notional,
            depth_rank=rank,
            event_type=event_type,  # type: ignore[arg-type]
            timestamp=now_ms,
        )

    def get_recent(self, limit: int = 50) -> list[LargeOrderEvent]:
        return list(self._recent)[-limit:]

    def get_current_walls(self, snapshot: OrderBookL2Snapshot) -> dict[str, list[dict[str, Any]]]:
        """Return currently visible large orders (bid walls and ask walls)."""
        result: dict[str, list[dict[str, Any]]] = {"bid_walls": [], "ask_walls": []}

        for rank, level in enumerate(snapshot.bids):
            notional = level.price * level.quantity
            if notional >= self._threshold_usd:
                result["bid_walls"].append({
                    "price": level.price,
                    "quantity": level.quantity,
                    "notional_usd": notional,
                    "rank": rank,
                })

        for rank, level in enumerate(snapshot.asks):
            notional = level.price * level.quantity
            if notional >= self._threshold_usd:
                result["ask_walls"].append({
                    "price": level.price,
                    "quantity": level.quantity,
                    "notional_usd": notional,
                    "rank": rank,
                })

        return result
