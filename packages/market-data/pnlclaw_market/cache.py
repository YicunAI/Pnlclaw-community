"""TTL + LRU cache for market data (tickers and klines).

Provides fast in-memory lookups, automatic TTL expiration,
and LRU eviction when the cache exceeds its configured maximum size.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Generic, TypeVar

from pnlclaw_types.market import KlineEvent, TickerEvent

V = TypeVar("V")


class _TTLEntry(Generic[V]):
    """Internal cache entry with expiry tracking."""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: V, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at


class TTLLRUCache(Generic[V]):
    """Thread-safe TTL + LRU cache.

    Items expire after *ttl_seconds*. When *max_size* is exceeded,
    the least-recently-used entry is evicted.

    Args:
        ttl_seconds: Time-to-live for each entry.
        max_size: Maximum number of entries before LRU eviction.
    """

    def __init__(self, ttl_seconds: float = 60.0, max_size: int = 1000) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._data: OrderedDict[str, _TTLEntry[V]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> V | None:
        """Return the value for *key* if present and not expired, else None.

        Moves the entry to the most-recently-used position on hit.
        """
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._data[key]
                return None
            # Mark as recently used
            self._data.move_to_end(key)
            return entry.value

    def put(self, key: str, value: V) -> None:
        """Insert or update *key* with *value*, resetting TTL."""
        now = time.monotonic()
        with self._lock:
            if key in self._data:
                del self._data[key]
            self._data[key] = _TTLEntry(value, now + self._ttl)
            self._data.move_to_end(key)
            self._evict_expired(now)
            self._evict_lru()

    def remove(self, key: str) -> bool:
        """Remove *key* from cache. Returns True if it existed."""
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._data.clear()

    @property
    def size(self) -> int:
        """Current number of entries (including possibly expired ones)."""
        with self._lock:
            return len(self._data)

    def _evict_expired(self, now: float) -> None:
        """Remove expired entries from the front (oldest first)."""
        keys_to_remove: list[str] = []
        for key, entry in self._data.items():
            if entry.expires_at <= now:
                keys_to_remove.append(key)
            else:
                break  # OrderedDict is insertion-ordered; older entries first
        for key in keys_to_remove:
            del self._data[key]

    def _evict_lru(self) -> None:
        """Evict least-recently-used entries if over max_size."""
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)


class MarketDataCache:
    """Specialized cache for market data events.

    Maintains separate TTL+LRU caches for tickers and klines,
    keyed by normalized symbol.

    Args:
        ttl_seconds: TTL for cached entries.
        max_size: Maximum entries per cache type.
    """

    def __init__(self, ttl_seconds: float = 60.0, max_size: int = 1000) -> None:
        self._tickers: TTLLRUCache[TickerEvent] = TTLLRUCache(ttl_seconds, max_size)
        self._klines: TTLLRUCache[KlineEvent] = TTLLRUCache(ttl_seconds, max_size)

    def get_ticker(self, symbol: str) -> TickerEvent | None:
        """Get cached ticker for *symbol*."""
        return self._tickers.get(symbol)

    def put_ticker(self, symbol: str, event: TickerEvent) -> None:
        """Cache a ticker event for *symbol*."""
        self._tickers.put(symbol, event)

    def get_kline(self, symbol: str) -> KlineEvent | None:
        """Get cached kline for *symbol*."""
        return self._klines.get(symbol)

    def put_kline(self, symbol: str, event: KlineEvent) -> None:
        """Cache a kline event for *symbol*."""
        self._klines.put(symbol, event)

    def clear(self) -> None:
        """Clear all caches."""
        self._tickers.clear()
        self._klines.clear()
