"""Sliding-window API rate limiter with Retry-After support.

Provides async-blocking rate limiting for exchange REST API calls.
Server-specified ``Retry-After`` delays take priority over the computed
sliding-window wait.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Async rate limiter using a sliding window of request timestamps.

    Contract:
        - :meth:`acquire` blocks until a request slot is available.
        - Sliding window: tracks *calls_per_window* requests within
          *window_ms* milliseconds.
        - :meth:`set_retry_after` parses HTTP ``Retry-After`` headers
          (seconds or HTTP-date). Server delay always takes priority.
    """

    def __init__(
        self,
        *,
        calls_per_window: int = 1200,
        window_ms: int = 60_000,
    ) -> None:
        if calls_per_window < 1:
            raise ValueError("calls_per_window must be >= 1")
        if window_ms < 1:
            raise ValueError("window_ms must be >= 1")

        self._calls_per_window = calls_per_window
        self._window_s = window_ms / 1000.0
        self._timestamps: deque[float] = deque()
        self._server_retry_until: float | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(self) -> None:
        """Block until a request is allowed under the rate limit."""
        async with self._lock:
            now = time.monotonic()

            # 1. Honour server-specified Retry-After.
            if self._server_retry_until is not None:
                wait = self._server_retry_until - now
                if wait > 0:
                    logger.debug("Rate limiter: server Retry-After wait %.2fs", wait)
                    await asyncio.sleep(wait)
                    now = time.monotonic()
                self._server_retry_until = None

            # 2. Prune timestamps outside the window.
            cutoff = now - self._window_s
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()

            # 3. If at capacity, wait until the oldest request exits the window.
            if len(self._timestamps) >= self._calls_per_window:
                oldest = self._timestamps[0]
                wait = (oldest + self._window_s) - now
                if wait > 0:
                    logger.debug("Rate limiter: sliding window wait %.2fs", wait)
                    await asyncio.sleep(wait)
                    now = time.monotonic()
                    # Re-prune after sleep.
                    cutoff = now - self._window_s
                    while self._timestamps and self._timestamps[0] <= cutoff:
                        self._timestamps.popleft()

            # 4. Record this request.
            self._timestamps.append(now)

    def set_retry_after(self, value: str | int | float) -> None:
        """Parse and apply a ``Retry-After`` header value.

        Args:
            value: Either a number (seconds to wait) or an HTTP-date string
                   (RFC 7231). Server-specified delay takes priority over
                   the sliding-window calculation.
        """
        delay_s = self._parse_retry_after(value)
        if delay_s is not None and delay_s > 0:
            self._server_retry_until = time.monotonic() + delay_s
            logger.info("Rate limiter: set server Retry-After to %.2fs", delay_s)

    def reset(self) -> None:
        """Clear all tracked state."""
        self._timestamps.clear()
        self._server_retry_until = None

    @property
    def remaining(self) -> int:
        """Number of requests that can be made right now without waiting."""
        now = time.monotonic()
        cutoff = now - self._window_s
        # Count active timestamps.
        active = sum(1 for t in self._timestamps if t > cutoff)
        return max(0, self._calls_per_window - active)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_retry_after(value: str | int | float) -> float | None:
        """Parse Retry-After as seconds or HTTP-date, returning delay in seconds."""
        if isinstance(value, (int, float)):
            return float(value)

        # Try numeric string first.
        try:
            return float(value)
        except ValueError:
            pass

        # Try HTTP-date format (RFC 7231).
        try:
            dt = parsedate_to_datetime(value)
            delay = dt.timestamp() - time.time()
            return max(0.0, delay)
        except Exception:
            logger.warning("Could not parse Retry-After value: %r", value)
            return None
