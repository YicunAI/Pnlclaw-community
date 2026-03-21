"""L2 orderbook snapshot store.

Maintains the latest L2 OrderBook snapshot for each symbol.
Thread-safe for concurrent reads and writes.
"""

from __future__ import annotations

import threading

from pnlclaw_types.market import OrderBookL2Snapshot


class SnapshotStore:
    """Thread-safe store for the latest L2 orderbook snapshot per symbol.

    Used by ``MarketDataService`` to cache snapshots received from
    ``BinanceL2Manager``, and queried by ``agent-runtime``'s market tools.

    Example::

        store = SnapshotStore()
        store.update("BTC/USDT", snapshot)
        latest = store.get_snapshot("BTC/USDT")
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, OrderBookL2Snapshot] = {}
        self._lock = threading.RLock()

    def update(self, symbol: str, snapshot: OrderBookL2Snapshot) -> None:
        """Store or replace the snapshot for *symbol*.

        Args:
            symbol: Normalized trading pair, e.g. ``"BTC/USDT"``.
            snapshot: The L2 orderbook snapshot to store.
        """
        with self._lock:
            self._snapshots[symbol] = snapshot

    def get_snapshot(self, symbol: str) -> OrderBookL2Snapshot | None:
        """Return the latest snapshot for *symbol*, or None if unavailable.

        Args:
            symbol: Normalized trading pair.
        """
        with self._lock:
            return self._snapshots.get(symbol)

    def remove(self, symbol: str) -> bool:
        """Remove the snapshot for *symbol*. Returns True if it existed."""
        with self._lock:
            if symbol in self._snapshots:
                del self._snapshots[symbol]
                return True
            return False

    def symbols(self) -> list[str]:
        """Return all symbols with stored snapshots."""
        with self._lock:
            return list(self._snapshots.keys())

    def clear(self) -> None:
        """Remove all stored snapshots."""
        with self._lock:
            self._snapshots.clear()

    @property
    def size(self) -> int:
        """Number of symbols currently stored."""
        with self._lock:
            return len(self._snapshots)
