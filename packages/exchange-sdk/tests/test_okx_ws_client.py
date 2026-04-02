"""Tests for OKX WebSocket client with mocked connections."""

from __future__ import annotations

import json

import pytest

from pnlclaw_exchange.exchanges.okx.ws_client import OKXWSClient
from pnlclaw_types.market import KlineEvent, TickerEvent


class MockOKXConnection:
    """Simulated OKX WebSocket connection."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self._messages: list[str] = []
        self._closed = False

    def queue(self, msg: dict) -> None:
        self._messages.append(json.dumps(msg))

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self._closed = True

    def __aiter__(self) -> MockOKXConnection:
        return self

    async def __anext__(self) -> str:
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)


@pytest.fixture
def mock_public_ws() -> MockOKXConnection:
    return MockOKXConnection()


@pytest.fixture
def mock_business_ws() -> MockOKXConnection:
    return MockOKXConnection()


class TestOKXWSClientSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_ticker(
        self, mock_public_ws: MockOKXConnection, mock_business_ws: MockOKXConnection
    ) -> None:
        client = OKXWSClient()
        client._ws_public = mock_public_ws  # type: ignore[assignment]
        client._ws_business = mock_business_ws  # type: ignore[assignment]

        await client.subscribe_ticker(["BTC-USDT", "ETH-USDT"])

        assert len(mock_public_ws.sent) == 1
        msg = json.loads(mock_public_ws.sent[0])
        assert msg["op"] == "subscribe"
        assert len(msg["args"]) == 2
        assert msg["args"][0] == {"channel": "tickers", "instId": "BTC-USDT"}
        assert len(mock_business_ws.sent) == 0

    @pytest.mark.asyncio
    async def test_subscribe_kline(
        self, mock_public_ws: MockOKXConnection, mock_business_ws: MockOKXConnection
    ) -> None:
        client = OKXWSClient()
        client._ws_public = mock_public_ws  # type: ignore[assignment]
        client._ws_business = mock_business_ws  # type: ignore[assignment]

        await client.subscribe_kline(["BTC-USDT"], interval="1H")

        assert len(mock_business_ws.sent) == 1
        msg = json.loads(mock_business_ws.sent[0])
        assert msg["op"] == "subscribe"
        assert msg["args"][0] == {"channel": "candle1H", "instId": "BTC-USDT"}
        assert len(mock_public_ws.sent) == 0


class TestOKXWSClientRouting:
    @pytest.mark.asyncio
    async def test_route_ticker(self) -> None:
        received: list[TickerEvent] = []
        client = OKXWSClient(on_ticker=received.append)

        await client._route_message(
            {
                "arg": {"channel": "tickers", "instId": "BTC-USDT"},
                "data": [
                    {
                        "last": "70000",
                        "bidPx": "69999",
                        "askPx": "70001",
                        "open24h": "69000",
                        "vol24h": "5000",
                        "ts": "1700000000000",
                    }
                ],
            }
        )

        assert len(received) == 1
        assert received[0].symbol == "BTC/USDT"
        assert received[0].last_price == 70000.0

    @pytest.mark.asyncio
    async def test_route_kline(self) -> None:
        received: list[KlineEvent] = []
        client = OKXWSClient(on_kline=received.append)

        await client._route_message(
            {
                "arg": {"channel": "candle1H", "instId": "ETH-USDT"},
                "data": [["1700000000000", "2200", "2250", "2180", "2240", "500", "1100000", "1100000", "1"]],
            }
        )

        assert len(received) == 1
        assert received[0].symbol == "ETH/USDT"
        assert received[0].close == 2240.0
        assert received[0].interval == "1h"
        assert received[0].closed is True

    @pytest.mark.asyncio
    async def test_skip_subscribe_ack(self) -> None:
        received: list[TickerEvent] = []
        client = OKXWSClient(on_ticker=received.append)

        await client._route_message(
            {
                "event": "subscribe",
                "arg": {"channel": "tickers", "instId": "BTC-USDT"},
            }
        )

        assert len(received) == 0


class TestOKXWSClientSubscriptions:
    @pytest.mark.asyncio
    async def test_subscriptions_tracked(
        self, mock_public_ws: MockOKXConnection, mock_business_ws: MockOKXConnection
    ) -> None:
        client = OKXWSClient()
        client._ws_public = mock_public_ws  # type: ignore[assignment]
        client._ws_business = mock_business_ws  # type: ignore[assignment]

        await client.subscribe_ticker(["BTC-USDT"])
        await client.subscribe_kline(["BTC-USDT"])

        assert "tickers:BTC-USDT" in client.subscriptions
        assert "candle1H:BTC-USDT" in client.subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe_removes(
        self, mock_public_ws: MockOKXConnection, mock_business_ws: MockOKXConnection
    ) -> None:
        client = OKXWSClient()
        client._ws_public = mock_public_ws  # type: ignore[assignment]
        client._ws_business = mock_business_ws  # type: ignore[assignment]

        await client.subscribe_ticker(["BTC-USDT"])
        await client.unsubscribe(["tickers:BTC-USDT"])

        assert "tickers:BTC-USDT" not in client.subscriptions
