"""Tests for StallWatchdog."""

from __future__ import annotations

import asyncio

import pytest

from pnlclaw_exchange.base.stall_watchdog import StallTimeoutMeta, StallWatchdog


@pytest.mark.asyncio
async def test_timeout_fires_after_idle() -> None:
    """Timeout callback fires when idle exceeds threshold."""
    fired: list[StallTimeoutMeta] = []

    wd = StallWatchdog(
        timeout_s=0.1,
        check_interval_s=0.03,
        on_timeout=lambda meta: fired.append(meta),
    )
    await wd.start()
    wd.arm()

    # Wait for timeout to fire.
    await asyncio.sleep(0.25)
    wd.stop()

    assert len(fired) == 1
    assert fired[0].idle_s >= 0.1
    assert fired[0].timeout_s == 0.1


@pytest.mark.asyncio
async def test_touch_resets_timer() -> None:
    """Calling touch() prevents the timeout from firing."""
    fired: list[StallTimeoutMeta] = []

    wd = StallWatchdog(
        timeout_s=0.1,
        check_interval_s=0.03,
        on_timeout=lambda meta: fired.append(meta),
    )
    await wd.start()
    wd.arm()

    # Touch repeatedly within the timeout window.
    for _ in range(5):
        await asyncio.sleep(0.04)
        wd.touch()

    wd.stop()
    assert len(fired) == 0


@pytest.mark.asyncio
async def test_disarm_prevents_timeout() -> None:
    """Disarming the watchdog prevents the timeout."""
    fired: list[StallTimeoutMeta] = []

    wd = StallWatchdog(
        timeout_s=0.08,
        check_interval_s=0.02,
        on_timeout=lambda meta: fired.append(meta),
    )
    await wd.start()
    wd.arm()
    wd.disarm()

    await asyncio.sleep(0.15)
    wd.stop()

    assert len(fired) == 0


@pytest.mark.asyncio
async def test_stop_prevents_further_checks() -> None:
    """Stopping the watchdog prevents any future timeout."""
    fired: list[StallTimeoutMeta] = []

    wd = StallWatchdog(
        timeout_s=0.05,
        check_interval_s=0.02,
        on_timeout=lambda meta: fired.append(meta),
    )
    await wd.start()
    wd.arm()
    wd.stop()

    await asyncio.sleep(0.1)

    assert len(fired) == 0
    assert wd.is_stopped is True
    assert wd.is_armed is False


@pytest.mark.asyncio
async def test_timeout_fires_only_once_per_arm_cycle() -> None:
    """After auto-disarm, timeout should not fire again until re-armed."""
    fired: list[StallTimeoutMeta] = []

    wd = StallWatchdog(
        timeout_s=0.05,
        check_interval_s=0.02,
        on_timeout=lambda meta: fired.append(meta),
    )
    await wd.start()
    wd.arm()

    # Wait long enough for multiple check intervals.
    await asyncio.sleep(0.25)
    wd.stop()

    # Should have fired exactly once (auto-disarm after first fire).
    assert len(fired) == 1


@pytest.mark.asyncio
async def test_rearm_allows_new_timeout() -> None:
    """After re-arming, the watchdog can fire again."""
    fired: list[StallTimeoutMeta] = []

    wd = StallWatchdog(
        timeout_s=0.05,
        check_interval_s=0.02,
        on_timeout=lambda meta: fired.append(meta),
    )
    await wd.start()

    # First cycle.
    wd.arm()
    await asyncio.sleep(0.12)
    assert len(fired) == 1

    # Re-arm for second cycle.
    wd.arm()
    await asyncio.sleep(0.12)
    wd.stop()

    assert len(fired) == 2


@pytest.mark.asyncio
async def test_async_callback() -> None:
    """on_timeout works with async callbacks."""
    fired: list[StallTimeoutMeta] = []

    async def handler(meta: StallTimeoutMeta) -> None:
        fired.append(meta)

    wd = StallWatchdog(
        timeout_s=0.05,
        check_interval_s=0.02,
        on_timeout=handler,
    )
    await wd.start()
    wd.arm()
    await asyncio.sleep(0.15)
    wd.stop()

    assert len(fired) == 1


@pytest.mark.asyncio
async def test_is_armed_property() -> None:
    wd = StallWatchdog(timeout_s=1.0)
    assert wd.is_armed is False

    wd.arm()
    assert wd.is_armed is True

    wd.disarm()
    assert wd.is_armed is False

    wd.arm()
    wd.stop()
    assert wd.is_armed is False


def test_invalid_timeout_raises() -> None:
    with pytest.raises(ValueError, match="positive"):
        StallWatchdog(timeout_s=0)

    with pytest.raises(ValueError, match="positive"):
        StallWatchdog(timeout_s=-1)
