"""Liquidation aggregator — sliding-window statistics over forced liquidations.

Maintains multiple time windows (15m, 30m, 1h, 4h, 24h) and computes
aggregate statistics on the fly.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from pnlclaw_types.derivatives import LiquidationEvent, LiquidationStats

logger = logging.getLogger(__name__)

WINDOW_DEFS: dict[str, int] = {
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "24h": 24 * 60 * 60_000,
}

_MAX_EVENTS = 10_000


class LiquidationAggregator:
    """Aggregate liquidation events into sliding-window statistics.

    Usage::

        agg = LiquidationAggregator()
        agg.on_stats_update(my_callback)
        agg.process(liquidation_event)
        stats = agg.get_stats("1h")
    """

    def __init__(self) -> None:
        self._events: deque[LiquidationEvent] = deque(maxlen=_MAX_EVENTS)
        self._callbacks: list[Callable[[LiquidationStats], Any]] = []
        self._stats_cache: dict[str, LiquidationStats] = {}

    def on_stats_update(self, callback: Callable[[LiquidationStats], Any]) -> None:
        self._callbacks.append(callback)

    def process(self, event: LiquidationEvent) -> None:
        """Ingest a liquidation event and update all windows."""
        self._events.append(event)
        self._purge_old()
        self._recompute_all()

    def get_stats(self, window: str = "1h", symbol: str = "ALL") -> LiquidationStats | None:
        """Get the latest stats for a time window."""
        key = f"{symbol}:{window}"
        return self._stats_cache.get(key)

    def get_all_stats(self, symbol: str = "ALL") -> dict[str, LiquidationStats]:
        """Get stats for all windows."""
        result: dict[str, LiquidationStats] = {}
        for window in WINDOW_DEFS:
            key = f"{symbol}:{window}"
            if key in self._stats_cache:
                result[window] = self._stats_cache[key]
        return result

    def get_recent_events(self, limit: int = 50) -> list[LiquidationEvent]:
        """Return the most recent raw liquidation events."""
        return list(self._events)[-limit:]

    def _purge_old(self) -> None:
        """Remove events older than 24h."""
        cutoff = int(time.time() * 1000) - WINDOW_DEFS["24h"]
        while self._events and self._events[0].timestamp < cutoff:
            self._events.popleft()

    def _recompute_all(self) -> None:
        """Recompute stats for all windows."""
        now_ms = int(time.time() * 1000)

        for window, ms in WINDOW_DEFS.items():
            cutoff = now_ms - ms
            filtered = [e for e in self._events if e.timestamp >= cutoff]

            long_events = [e for e in filtered if e.side == "long"]
            short_events = [e for e in filtered if e.side == "short"]

            long_usd = sum(e.notional_usd for e in long_events)
            short_usd = sum(e.notional_usd for e in short_events)
            all_notional = [e.notional_usd for e in filtered]
            largest = max(all_notional) if all_notional else 0.0

            stats = LiquidationStats(
                symbol="ALL",
                window=window,
                long_liquidated_usd=long_usd,
                short_liquidated_usd=short_usd,
                total_liquidated_usd=long_usd + short_usd,
                long_count=len(long_events),
                short_count=len(short_events),
                largest_single_usd=largest,
                timestamp=now_ms,
            )
            key = f"ALL:{window}"
            self._stats_cache[key] = stats

            for cb in self._callbacks:
                try:
                    cb(stats)
                except Exception:
                    logger.exception("Error in liquidation stats callback")
