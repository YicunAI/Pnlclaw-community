"""Three-state stall detector for WebSocket connections.

Distilled from OpenClaw's ``src/channels/transport/stall-watchdog.ts``.
Monitors for data stalls and triggers a callback when no messages are
received within the configured timeout period.

States:
    - **armed**: actively monitoring for stalls.
    - **idle**: watchdog task running but not armed (disarmed).
    - **stopped**: background task cancelled, no monitoring.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

Callback = Callable[..., Any]


@dataclass
class StallTimeoutMeta:
    """Metadata passed to the ``on_timeout`` callback when a stall fires."""

    idle_s: float
    timeout_s: float


class StallWatchdog:
    """Detect WebSocket data stalls via periodic idle-time checks.

    Contract:
        - Three states: armed / idle (disarmed) / stopped.
        - :meth:`arm` begins monitoring; :meth:`touch` resets the timer.
        - :meth:`disarm` pauses monitoring without stopping the task.
        - Timeout fires at most once per :meth:`arm` cycle (auto-disarms).
        - Uses ``time.monotonic()`` to avoid clock-skew issues.
    """

    def __init__(
        self,
        *,
        timeout_s: float = 30.0,
        check_interval_s: float | None = None,
        on_timeout: Callback | None = None,
        label: str = "ws-watchdog",
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")

        self._timeout_s = timeout_s
        self._check_interval_s = check_interval_s or min(5.0, max(0.25, timeout_s / 6))
        self._on_timeout = on_timeout
        self._label = label

        self._armed: bool = False
        self._stopped: bool = False
        self._last_activity: float = 0.0
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background check loop."""
        if self._task is not None and not self._task.done():
            return
        self._stopped = False
        self._task = asyncio.create_task(self._check_loop(), name=self._label)

    def arm(self) -> None:
        """Begin monitoring for stalls. Resets the idle timer."""
        if self._stopped:
            return
        self._armed = True
        self._last_activity = time.monotonic()

    def touch(self) -> None:
        """Reset the idle timer. Call on every received message."""
        if self._stopped:
            return
        self._last_activity = time.monotonic()

    def disarm(self) -> None:
        """Pause monitoring without stopping the background task."""
        self._armed = False

    def stop(self) -> None:
        """Stop the watchdog entirely and cancel the background task."""
        self._stopped = True
        self._armed = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            self._task = None

    @property
    def is_armed(self) -> bool:
        """Whether the watchdog is actively monitoring."""
        return self._armed and not self._stopped

    @property
    def is_stopped(self) -> bool:
        """Whether the watchdog has been fully stopped."""
        return self._stopped

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _check_loop(self) -> None:
        """Periodically check for stalls while not stopped."""
        try:
            while not self._stopped:
                await asyncio.sleep(self._check_interval_s)
                if self._stopped:
                    break
                await self._check()
        except asyncio.CancelledError:
            pass

    async def _check(self) -> None:
        """Fire the timeout callback if idle time exceeds the threshold."""
        if not self._armed or self._stopped:
            return

        now = time.monotonic()
        idle_s = now - self._last_activity

        if idle_s >= self._timeout_s:
            # Auto-disarm — timeout fires at most once per arm cycle.
            self._armed = False
            meta = StallTimeoutMeta(idle_s=idle_s, timeout_s=self._timeout_s)
            logger.warning(
                "[%s] Stall detected: %.1fs idle (timeout=%.1fs)",
                self._label,
                idle_s,
                self._timeout_s,
            )
            if self._on_timeout is not None:
                result = self._on_timeout(meta)
                if inspect.isawaitable(result):
                    await result
