"""Tests for BaseWSClient ABC."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pnlclaw_exchange.base.ws_client import BaseWSClient
from pnlclaw_exchange.types import WSClientConfig


# ---------------------------------------------------------------------------
# Concrete test implementation
# ---------------------------------------------------------------------------


class StubWSClient(BaseWSClient):
    """Minimal concrete subclass for testing the ABC."""

    def __init__(self, **kwargs: Any) -> None:
        config = WSClientConfig(url="wss://test.example.com/ws", exchange="test")
        super().__init__(config, **kwargs)
        self.connect_called = False
        self.close_called = False

    async def connect(self) -> None:
        self.connect_called = True
        await self._dispatch_connect()

    async def subscribe(self, streams: list[str]) -> None:
        self._subscriptions.update(streams)

    async def unsubscribe(self, streams: list[str]) -> None:
        self._subscriptions -= set(streams)

    async def close(self) -> None:
        self.close_called = True
        await self._dispatch_disconnect(code=1000, reason="normal")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initial_state() -> None:
    client = StubWSClient()
    assert client.is_connected is False
    assert client.subscriptions == frozenset()
    assert client.config.exchange == "test"


@pytest.mark.asyncio
async def test_connect_sets_connected() -> None:
    client = StubWSClient()
    await client.connect()
    assert client.is_connected is True
    assert client.connect_called is True


@pytest.mark.asyncio
async def test_close_sets_disconnected() -> None:
    client = StubWSClient()
    await client.connect()
    await client.close()
    assert client.is_connected is False
    assert client.close_called is True


@pytest.mark.asyncio
async def test_subscribe_tracks_streams() -> None:
    client = StubWSClient()
    await client.subscribe(["btcusdt@ticker", "ethusdt@trade"])
    assert client.subscriptions == frozenset({"btcusdt@ticker", "ethusdt@trade"})


@pytest.mark.asyncio
async def test_unsubscribe_removes_streams() -> None:
    client = StubWSClient()
    await client.subscribe(["btcusdt@ticker", "ethusdt@trade"])
    await client.unsubscribe(["btcusdt@ticker"])
    assert client.subscriptions == frozenset({"ethusdt@trade"})


@pytest.mark.asyncio
async def test_subscriptions_returns_frozen_copy() -> None:
    client = StubWSClient()
    await client.subscribe(["stream_a"])
    subs = client.subscriptions
    # Mutating the internal set must not affect the returned frozenset.
    await client.subscribe(["stream_b"])
    assert "stream_b" not in subs


@pytest.mark.asyncio
async def test_on_message_callback_sync() -> None:
    received: list[dict[str, Any]] = []
    client = StubWSClient(on_message=lambda data: received.append(data))
    await client._dispatch_message({"test": True})
    assert received == [{"test": True}]


@pytest.mark.asyncio
async def test_on_message_callback_async() -> None:
    received: list[dict[str, Any]] = []

    async def handler(data: dict[str, Any]) -> None:
        received.append(data)

    client = StubWSClient(on_message=handler)
    await client._dispatch_message({"async": True})
    assert received == [{"async": True}]


@pytest.mark.asyncio
async def test_on_error_callback() -> None:
    errors: list[Exception] = []
    client = StubWSClient(on_error=lambda e: errors.append(e))
    err = RuntimeError("boom")
    await client._dispatch_error(err)
    assert errors == [err]


@pytest.mark.asyncio
async def test_on_connect_callback() -> None:
    called = []
    client = StubWSClient(on_connect=lambda: called.append(True))
    await client.connect()
    assert called == [True]


@pytest.mark.asyncio
async def test_on_disconnect_callback() -> None:
    disconnects: list[tuple[int, str]] = []
    client = StubWSClient(on_disconnect=lambda c, r: disconnects.append((c, r)))
    await client.connect()
    await client.close()
    assert disconnects == [(1000, "normal")]


@pytest.mark.asyncio
async def test_no_callback_does_not_raise() -> None:
    """Dispatching without a callback set must not raise."""
    client = StubWSClient()
    await client._dispatch_message({"data": 1})
    await client._dispatch_error(RuntimeError("ignored"))
    await client._dispatch_connect()
    await client._dispatch_disconnect()
