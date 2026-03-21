"""TTL-based deduplicator with size cap."""

from __future__ import annotations

import threading
import time


class Deduplicator:
    """Deduplicates keys within a TTL window.

    Thread-safe. Expired entries are cleaned on access. If *max_size* is
    reached, the oldest entries are evicted regardless of TTL.

    Args:
        ttl_seconds: Time-to-live for each key.
        max_size: Maximum number of tracked keys before forced eviction.
    """

    def __init__(self, ttl_seconds: float = 60.0, max_size: int = 10_000) -> None:
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._seen: dict[str, float] = {}  # key → expiry timestamp
        self._lock = threading.Lock()

    def is_duplicate(self, key: str) -> bool:
        """Check if *key* was seen within the TTL window.

        If not a duplicate, records the key. Returns True if duplicate.
        """
        now = time.monotonic()
        with self._lock:
            self._cleanup(now)
            if key in self._seen and self._seen[key] > now:
                return True
            self._seen[key] = now + self._ttl
            self._enforce_size()
            return False

    def _cleanup(self, now: float) -> None:
        """Remove expired entries."""
        expired = [k for k, exp in self._seen.items() if exp <= now]
        for k in expired:
            del self._seen[k]

    def _enforce_size(self) -> None:
        """Evict oldest entries if over max_size."""
        if len(self._seen) <= self._max_size:
            return
        # Sort by expiry, remove the oldest (closest to now)
        sorted_keys = sorted(self._seen, key=lambda k: self._seen[k])
        to_remove = len(self._seen) - self._max_size
        for k in sorted_keys[:to_remove]:
            del self._seen[k]

    @property
    def size(self) -> int:
        """Current number of tracked keys."""
        with self._lock:
            return len(self._seen)

    def clear(self) -> None:
        """Remove all tracked keys."""
        with self._lock:
            self._seen.clear()
