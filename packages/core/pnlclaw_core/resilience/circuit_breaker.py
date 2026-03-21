"""Circuit breaker: three-state (closed/open/half-open) failure protection."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is attempted on an open circuit."""


class CircuitBreaker:
    """Async circuit breaker with configurable thresholds.

    Args:
        failure_threshold: Consecutive failures before opening.
        recovery_timeout: Seconds to wait before transitioning to half-open.
        half_open_max_calls: Max test calls in half-open state.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        """Current circuit state, checking for automatic transitions."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Execute *fn* through the circuit breaker.

        Raises:
            CircuitOpenError: If the circuit is open and recovery time hasn't elapsed.
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit is open, retry after {self._recovery_timeout}s"
            )

        if current_state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self._half_open_max_calls:
                raise CircuitOpenError("Circuit half-open: max test calls reached")
            self._half_open_calls += 1

        try:
            result = await fn()
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Reset counters on success."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def _on_failure(self) -> None:
        """Increment failure count, possibly opening the circuit."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset the circuit to closed."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
