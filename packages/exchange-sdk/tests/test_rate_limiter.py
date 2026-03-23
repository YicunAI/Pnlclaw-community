"""Tests for SlidingWindowRateLimiter."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from pnlclaw_exchange.base.rate_limiter import SlidingWindowRateLimiter


@pytest.mark.asyncio
async def test_basic_rate_limiting() -> None:
    """N+1 th request should be delayed when window is full."""
    limiter = SlidingWindowRateLimiter(calls_per_window=3, window_ms=500)

    start = time.monotonic()
    for _ in range(3):
        await limiter.acquire()
    elapsed_fast = time.monotonic() - start

    # First 3 should be near-instant.
    assert elapsed_fast < 0.1

    # 4th should wait for the window to slide.
    await limiter.acquire()
    elapsed_total = time.monotonic() - start
    assert elapsed_total >= 0.4  # ~500ms window


@pytest.mark.asyncio
async def test_sliding_window_allows_after_expiry() -> None:
    """After the window expires, requests should be allowed again."""
    limiter = SlidingWindowRateLimiter(calls_per_window=2, window_ms=200)

    await limiter.acquire()
    await limiter.acquire()

    # Wait for window to expire.
    await asyncio.sleep(0.25)

    # Should be able to acquire immediately.
    start = time.monotonic()
    await limiter.acquire()
    assert time.monotonic() - start < 0.1


@pytest.mark.asyncio
async def test_remaining_property() -> None:
    """remaining should reflect available slots."""
    limiter = SlidingWindowRateLimiter(calls_per_window=5, window_ms=1000)
    assert limiter.remaining == 5

    await limiter.acquire()
    assert limiter.remaining == 4

    await limiter.acquire()
    assert limiter.remaining == 3


@pytest.mark.asyncio
async def test_set_retry_after_numeric() -> None:
    """set_retry_after with numeric value should delay next acquire."""
    limiter = SlidingWindowRateLimiter(calls_per_window=100, window_ms=60_000)
    limiter.set_retry_after(0.2)  # 200ms

    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15  # Allow some tolerance


@pytest.mark.asyncio
async def test_set_retry_after_string_numeric() -> None:
    """set_retry_after with string numeric value."""
    limiter = SlidingWindowRateLimiter(calls_per_window=100, window_ms=60_000)
    limiter.set_retry_after("0.2")

    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15


@pytest.mark.asyncio
async def test_set_retry_after_http_date() -> None:
    """set_retry_after with HTTP-date string parses correctly."""
    limiter = SlidingWindowRateLimiter(calls_per_window=100, window_ms=60_000)
    # HTTP-date has 1-second resolution, so use a delay large enough.
    future = datetime.now(UTC) + timedelta(seconds=2)
    http_date = format_datetime(future, usegmt=True)

    # Verify that parsing produces a positive delay that gets stored.
    delay = limiter._parse_retry_after(http_date)
    assert delay is not None
    assert delay > 0.5  # Should be ~2 seconds


@pytest.mark.asyncio
async def test_server_retry_after_overrides_window() -> None:
    """Server Retry-After should take priority even when window has slots."""
    limiter = SlidingWindowRateLimiter(calls_per_window=100, window_ms=60_000)
    limiter.set_retry_after(0.2)

    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start

    # Should have waited for server delay despite having lots of slots.
    assert elapsed >= 0.15


@pytest.mark.asyncio
async def test_reset_clears_state() -> None:
    """reset() should clear all tracked state."""
    limiter = SlidingWindowRateLimiter(calls_per_window=2, window_ms=10_000)
    await limiter.acquire()
    await limiter.acquire()
    assert limiter.remaining == 0

    limiter.reset()
    assert limiter.remaining == 2


def test_invalid_config_raises() -> None:
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(calls_per_window=0)
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(window_ms=0)
