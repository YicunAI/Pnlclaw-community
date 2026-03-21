"""Exponential backoff policy for retry and reconnection logic."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BackoffPolicy:
    """Configurable exponential backoff with jitter.

    Args:
        initial: Base delay in seconds for the first retry.
        max_delay: Upper bound on delay in seconds.
        factor: Multiplier applied per attempt (exponential base).
        jitter: If True, add random jitter up to ±25% of the computed delay.
    """

    initial: float = 1.0
    max_delay: float = 60.0
    factor: float = 2.0
    jitter: bool = True

    def calculate_delay(self, attempt: int) -> float:
        """Return the delay in seconds for the given attempt (0-indexed).

        Args:
            attempt: Zero-based attempt number.

        Returns:
            Delay in seconds, clamped to *max_delay*.
        """
        delay = self.initial * (self.factor ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay *= 0.75 + random.random() * 0.5  # ±25%
        return delay
