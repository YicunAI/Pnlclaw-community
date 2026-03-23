"""Tests for BinanceWSClient."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from pnlclaw_exchange.exchanges.binance.normalizer import BinanceDepthDelta
from pnlclaw_exchange.exchanges.binance.ws_client import BinanceWSClient
from pnlclaw_types.market import KlineEvent, TickerEvent, TradeEvent

# ---------------------------------------------------------------------------
# Mock WebSocket
# ---------------------------------------------------------------------------


class FakeWSProtocol:
    """Fake websockets ClientConnection for testing."""

    def __init__(self, messages: list[dict[str, Any]] | None = None) -> None:
        self._messages = [json.dumps(m) for m in (messages or [])]
        self._sent: list[str] = []
        self._closed = False

    async def send(self, data: str) -> None:
        self._sent.append(data)

    async def close(self) -> None:
        self._closed = True

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)

    @property
    def sent_messages(self) -> list[dict[str, Any]]:
        return [json.loads(s) for s in self._sent]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_sends_correct_message(
    sample_binance_ticker: dict[str, Any],
) -> None:
    fake_ws = FakeWSProtocol([sample_binance_ticker])

    with patch(
        "pnlclaw_exchange.exchanges.binance.ws_client.websockets.asyncio.client.connect",
        new_callable=AsyncMock,
        return_value=fake_ws,
    ):
        client = BinanceWSClient()
        await client.connect()
        await client.subscribe(["btcusdt@ticker"])

    assert len(fake_ws.sent_messages) == 1
    msg = fake_ws.sent_messages[0]
    assert msg["method"] == "SUBSCRIBE"
    assert msg["params"] == ["btcusdt@ticker"]
    assert "id" in msg

    await client.close()


@pytest.mark.asyncio
async def test_unsubscribe_sends_correct_message() -> None:
    fake_ws = FakeWSProtocol()

    with patch(
        "pnlclaw_exchange.exchanges.binance.ws_client.websockets.asyncio.client.connect",
        new_callable=AsyncMock,
        return_value=fake_ws,
    ):
        client = BinanceWSClient()
        await client.connect()
        await client.subscribe(["btcusdt@ticker"])
        await client.unsubscribe(["btcusdt@ticker"])

    assert len(fake_ws.sent_messages) == 2
    unsub = fake_ws.sent_messages[1]
    assert unsub["method"] == "UNSUBSCRIBE"
    assert unsub["params"] == ["btcusdt@ticker"]
    assert client.subscriptions == frozenset()

    await client.close()


@pytest.mark.asyncio
async def test_ticker_callback_fires(
    sample_binance_ticker: dict[str, Any],
) -> None:
    received: list[TickerEvent] = []

    fake_ws = FakeWSProtocol([sample_binance_ticker])

    with patch(
        "pnlclaw_exchange.exchanges.binance.ws_client.websockets.asyncio.client.connect",
        new_callable=AsyncMock,
        return_value=fake_ws,
    ):
        client = BinanceWSClient(on_ticker=lambda e: received.append(e))
        await client.connect()

        # Let the receive loop process messages.
        await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].symbol == "BTC/USDT"
    assert received[0].last_price == 67000.0

    await client.close()


@pytest.mark.asyncio
async def test_trade_callback_fires(
    sample_binance_trade: dict[str, Any],
) -> None:
    received: list[TradeEvent] = []

    fake_ws = FakeWSProtocol([sample_binance_trade])

    with patch(
        "pnlclaw_exchange.exchanges.binance.ws_client.websockets.asyncio.client.connect",
        new_callable=AsyncMock,
        return_value=fake_ws,
    ):
        client = BinanceWSClient(on_trade=lambda e: received.append(e))
        await client.connect()
        await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].side == "buy"

    await client.close()


@pytest.mark.asyncio
async def test_kline_callback_fires(
    sample_binance_kline: dict[str, Any],
) -> None:
    received: list[KlineEvent] = []

    fake_ws = FakeWSProtocol([sample_binance_kline])

    with patch(
        "pnlclaw_exchange.exchanges.binance.ws_client.websockets.asyncio.client.connect",
        new_callable=AsyncMock,
        return_value=fake_ws,
    ):
        client = BinanceWSClient(on_kline=lambda e: received.append(e))
        await client.connect()
        await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].interval == "1h"
    assert received[0].closed is True

    await client.close()


@pytest.mark.asyncio
async def test_depth_callback_fires(
    sample_binance_depth_update: dict[str, Any],
) -> None:
    received: list[BinanceDepthDelta] = []

    fake_ws = FakeWSProtocol([sample_binance_depth_update])

    with patch(
        "pnlclaw_exchange.exchanges.binance.ws_client.websockets.asyncio.client.connect",
        new_callable=AsyncMock,
        return_value=fake_ws,
    ):
        client = BinanceWSClient(on_depth_update=lambda e: received.append(e))
        await client.connect()
        await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].first_update_id == 100001

    await client.close()


@pytest.mark.asyncio
async def test_combined_stream_format() -> None:
    """Messages in combined stream format should be unwrapped."""
    combined_msg = {
        "stream": "btcusdt@ticker",
        "data": {
            "e": "24hrTicker",
            "E": 1711000000000,
            "s": "BTCUSDT",
            "c": "67000.00",
            "b": "66999.50",
            "a": "67000.50",
            "v": "12345.67",
            "P": "2.35",
        },
    }

    received: list[TickerEvent] = []
    fake_ws = FakeWSProtocol([combined_msg])

    with patch(
        "pnlclaw_exchange.exchanges.binance.ws_client.websockets.asyncio.client.connect",
        new_callable=AsyncMock,
        return_value=fake_ws,
    ):
        client = BinanceWSClient(on_ticker=lambda e: received.append(e))
        await client.connect()
        await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].symbol == "BTC/USDT"

    await client.close()


@pytest.mark.asyncio
async def test_subscription_response_ignored() -> None:
    """Binance subscription confirmation messages should be skipped."""
    sub_response = {"result": None, "id": 1}
    raw_messages: list[dict[str, Any]] = []

    fake_ws = FakeWSProtocol([sub_response])

    with patch(
        "pnlclaw_exchange.exchanges.binance.ws_client.websockets.asyncio.client.connect",
        new_callable=AsyncMock,
        return_value=fake_ws,
    ):
        client = BinanceWSClient(on_message=lambda d: raw_messages.append(d))
        await client.connect()
        await asyncio.sleep(0.05)

    # Subscription response should not be passed to on_message.
    assert len(raw_messages) == 0

    await client.close()


class TestStreamName:
    def test_ticker(self) -> None:
        assert BinanceWSClient.stream_name("btcusdt", "ticker") == "btcusdt@ticker"

    def test_kline_with_interval(self) -> None:
        assert (
            BinanceWSClient.stream_name("btcusdt", "kline", interval="1h")
            == "btcusdt@kline_1h"
        )

    def test_depth(self) -> None:
        assert (
            BinanceWSClient.stream_name("btcusdt", "depth@100ms")
            == "btcusdt@depth@100ms"
        )

    def test_trade(self) -> None:
        assert BinanceWSClient.stream_name("ethusdt", "trade") == "ethusdt@trade"

    def test_uppercased_symbol_lowered(self) -> None:
        assert BinanceWSClient.stream_name("BTCUSDT", "ticker") == "btcusdt@ticker"
