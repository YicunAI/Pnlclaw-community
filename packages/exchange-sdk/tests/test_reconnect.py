"""Tests for ReconnectManager."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from pnlclaw_exchange.base.reconnect import ReconnectManager
from pnlclaw_exchange.base.ws_client import BaseWSClient
from pnlclaw_exchange.types import ReconnectConfig, WSClientConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeWSClient(BaseWSClient):
    """Fake WS client for testing reconnection logic."""

    def __init__(
        self,
        *,
        connect_side_effects: list[Exception | None] | None = None,
    ) -> None:
        config = WSClientConfig(url="wss://test/ws", exchange="test")
        super().__init__(config)
        self._connect_effects = list(connect_side_effects or [None])
        self._connect_index = 0
        self.connect_count = 0
        self.subscribe_calls: list[list[str]] = []

    async def connect(self) -> None:
        self.connect_count += 1
        if self._connect_index < len(self._connect_effects):
            effect = self._connect_effects[self._connect_index]
            self._connect_index += 1
        else:
            effect = self._connect_effects[-1]
        if effect is not None:
            raise effect
        await self._dispatch_connect()

    async def subscribe(self, streams: list[str]) -> None:
        self._subscriptions.update(streams)
        self.subscribe_calls.append(streams)

    async def unsubscribe(self, streams: list[str]) -> None:
        self._subscriptions -= set(streams)

    async def close(self) -> None:
        await self._dispatch_disconnect()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_connect_resets_attempt() -> None:
    """After a successful connect, attempt counter resets to 0."""
    client = FakeWSClient(connect_side_effects=[None])
    config = ReconnectConfig(initial_delay_s=0.01, max_delay_s=0.05)
    mgr = ReconnectManager(client, config)

    async def listen() -> None:
        await mgr.stop()

    mgr._listen = listen
    await mgr.run()

    assert mgr.attempt == 0
    assert client.connect_count == 1


@pytest.mark.asyncio
async def test_backoff_increases_on_failure() -> None:
    """Each failure increases the computed delay."""
    config = ReconnectConfig(
        initial_delay_s=1.0, max_delay_s=30.0, factor=2.0, jitter=0.0
    )
    mgr = ReconnectManager(FakeWSClient(), config)

    mgr._attempt = 1
    d1 = mgr._compute_delay()
    mgr._attempt = 2
    d2 = mgr._compute_delay()
    mgr._attempt = 3
    d3 = mgr._compute_delay()

    assert d1 < d2 < d3


@pytest.mark.asyncio
async def test_jitter_within_range() -> None:
    """Jitter should be within ±20% of the base delay."""
    config = ReconnectConfig(
        initial_delay_s=10.0, max_delay_s=30.0, factor=2.0, jitter=0.2
    )
    mgr = ReconnectManager(FakeWSClient(), config)
    mgr._attempt = 1

    delays = [mgr._compute_delay() for _ in range(200)]
    # Base delay for attempt 0 (used in compute: attempt-1) = 10.0
    # Jitter ±20% → [8.0, 12.0]
    assert all(7.9 <= d <= 12.1 for d in delays), f"Out of range: {min(delays)}, {max(delays)}"


@pytest.mark.asyncio
async def test_resubscribe_after_reconnect() -> None:
    """Subscriptions are restored after successful reconnection."""
    client = FakeWSClient(
        connect_side_effects=[None, ConnectionError("fail"), None]
    )
    # Pre-subscribe some streams.
    await client.subscribe(["btcusdt@ticker", "ethusdt@trade"])

    config = ReconnectConfig(initial_delay_s=0.01, max_delay_s=0.05)
    call_count = 0

    async def listen() -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("disconnect")
        # Second time — stop.
        await mgr.stop()

    mgr = ReconnectManager(client, config, listen=listen)
    await mgr.run()

    # Should have re-subscribed the streams.
    assert len(client.subscribe_calls) >= 2


@pytest.mark.asyncio
async def test_auth_error_stops_reconnect() -> None:
    """AUTH errors should stop the reconnection loop."""
    client = FakeWSClient(
        connect_side_effects=[Exception("401 unauthorized")]
    )
    config = ReconnectConfig(initial_delay_s=0.01)
    mgr = ReconnectManager(client, config)
    await mgr.run()

    # Should have stopped after 1 attempt (auth error).
    assert client.connect_count == 1
    assert mgr.is_running is False


@pytest.mark.asyncio
async def test_restart_rate_limit() -> None:
    """After max_restarts_per_hour, the loop should stop."""
    config = ReconnectConfig(
        initial_delay_s=0.001, max_delay_s=0.001, max_restarts_per_hour=3
    )
    client = FakeWSClient(
        connect_side_effects=[ConnectionError("fail")] * 10
    )
    mgr = ReconnectManager(client, config)
    await mgr.run()

    # Should have stopped after 3 failures (rate limit).
    assert client.connect_count <= 4  # 3 rate-limited + possibly 1 more


@pytest.mark.asyncio
async def test_stop_during_backoff() -> None:
    """Calling stop() during backoff should exit promptly."""
    client = FakeWSClient(connect_side_effects=[ConnectionError("fail")] * 10)
    config = ReconnectConfig(initial_delay_s=10.0, max_delay_s=60.0)
    mgr = ReconnectManager(client, config)

    async def stop_soon() -> None:
        await asyncio.sleep(0.05)
        await mgr.stop()

    t = asyncio.create_task(stop_soon())
    await mgr.run()
    await t

    assert mgr.is_running is False
