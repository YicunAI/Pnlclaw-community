"""Generic async retry with exponential backoff and jitter."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pnlclaw_core.resilience.backoff import BackoffPolicy

T = TypeVar("T")

logger = logging.getLogger(__name__)

ShouldRetry = Callable[[Exception], bool]


def _default_should_retry(exc: Exception) -> bool:
    """Retry on any exception by default."""
    return True


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    policy: BackoffPolicy | None = None,
    should_retry: ShouldRetry = _default_should_retry,
) -> T:
    """Execute *fn* with retries on failure.

    Args:
        fn: Async callable to execute.
        max_attempts: Maximum total attempts (including the first).
        policy: Backoff policy for delay calculation.
        should_retry: Predicate to decide whether to retry a given exception.

    Returns:
        The result of *fn* on success.

    Raises:
        The last exception if all attempts are exhausted.
    """
    if policy is None:
        policy = BackoffPolicy()

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= max_attempts or not should_retry(exc):
                raise
            delay = policy.calculate_delay(attempt)
            logger.debug(
                "Retry attempt %d/%d after %.2fs: %s",
                attempt + 1,
                max_attempts,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    # Unreachable, but satisfies type checker
    assert last_exc is not None
    raise last_exc
