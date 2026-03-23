"""WebSocket reconnection manager with exponential backoff.

Distilled from OpenClaw's WS reconnection loop: exponential backoff with
jitter, success-reset, subscription recovery, and hourly restart rate limiting.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from collections.abc import Awaitable, Callable

from pnlclaw_core.resilience.backoff import BackoffPolicy
from pnlclaw_core.resilience.error_classifier import ErrorCategory, classify_error
from pnlclaw_exchange.base.ws_client import BaseWSClient
from pnlclaw_exchange.types import ReconnectConfig

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = ReconnectConfig()


class ReconnectManager:
    """Manages WebSocket reconnection lifecycle with exponential backoff.

    Wraps a :class:`BaseWSClient` and orchestrates the reconnect loop:
    ``connect → resubscribe → listen → exception → backoff → retry``.

    Contract:
        - Exponential backoff: initial 1 s, max 30 s, factor 2.0, jitter ±20 %.
        - Resets attempt counter on successful connection.
        - Re-subscribes all active streams after reconnect.
        - Enforces a maximum of 10 restarts per hour.
        - AUTH errors stop the reconnection loop.
    """

    def __init__(
        self,
        client: BaseWSClient,
        config: ReconnectConfig | None = None,
        *,
        listen: Callable[..., Awaitable[None]] | None = None,
    ) -> None:
        self._client = client
        self._config = config or _DEFAULT_CONFIG
        self._listen = listen

        # Backoff (jitter applied manually for ±20%)
        self._backoff = BackoffPolicy(
            initial=self._config.initial_delay_s,
            max_delay=self._config.max_delay_s,
            factor=self._config.factor,
            jitter=False,
        )

        self._attempt: int = 0
        self._restart_timestamps: deque[float] = deque()
        self._running: bool = False
        self._shutdown_event: asyncio.Event = asyncio.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start the reconnection loop.

        Blocks until :meth:`stop` is called or an unrecoverable error occurs
        (e.g. authentication failure).
        """
        self._running = True
        self._shutdown_event.clear()

        while not self._shutdown_event.is_set():
            try:
                await self._client.connect()
                await self._resubscribe()

                # Successful connection — reset backoff.
                self._attempt = 0

                # Hand control to the caller's listen loop.
                if self._listen is not None:
                    await self._listen()
                else:
                    # Wait until shutdown or disconnection.
                    await self._shutdown_event.wait()

            except Exception as exc:
                category = classify_error(exc)

                if category == ErrorCategory.AUTH:
                    logger.error(
                        "Authentication error — stopping reconnect: %s", exc
                    )
                    break

                if not self._check_restart_rate():
                    logger.error(
                        "Restart rate limit exceeded (%d/hour) — pausing reconnect",
                        self._config.max_restarts_per_hour,
                    )
                    break

                self._attempt += 1
                delay = self._compute_delay()
                logger.warning(
                    "WebSocket error (attempt %d, category=%s, delay=%.2fs): %s",
                    self._attempt,
                    category.value,
                    delay,
                    exc,
                )

                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=delay
                    )
                    # Shutdown was requested during backoff.
                    break
                except TimeoutError:
                    # Backoff period elapsed — retry.
                    pass

        self._running = False

    async def stop(self) -> None:
        """Signal the reconnection loop to shut down gracefully."""
        self._shutdown_event.set()
        try:
            await self._client.close()
        except Exception:
            pass

    @property
    def is_running(self) -> bool:
        """Whether the reconnection loop is active."""
        return self._running

    @property
    def attempt(self) -> int:
        """Current attempt counter (resets on success)."""
        return self._attempt

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_delay(self) -> float:
        """Compute backoff delay with ±20 % jitter."""
        base: float = self._backoff.calculate_delay(self._attempt - 1)
        jitter_range: float = self._config.jitter
        jitter_factor = 1.0 - jitter_range + random.random() * 2 * jitter_range
        return base * jitter_factor

    def _check_restart_rate(self) -> bool:
        """Return True if a restart is allowed under the hourly rate limit."""
        now = time.monotonic()
        one_hour_ago = now - 3600.0

        # Prune timestamps older than 1 hour.
        while self._restart_timestamps and self._restart_timestamps[0] < one_hour_ago:
            self._restart_timestamps.popleft()

        if len(self._restart_timestamps) >= self._config.max_restarts_per_hour:
            return False

        self._restart_timestamps.append(now)
        return True

    async def _resubscribe(self) -> None:
        """Restore all active subscriptions after reconnect."""
        streams = list(self._client.subscriptions)
        if streams:
            logger.info("Re-subscribing to %d streams", len(streams))
            await self._client.subscribe(streams)
