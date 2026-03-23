"""Shared test fixtures for exchange-sdk tests."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Mock WebSocket connection
# ---------------------------------------------------------------------------


class MockWSConnection:
    """Mock WebSocket connection mimicking websockets.WebSocketClientProtocol."""

    def __init__(self, messages: list[dict[str, Any]] | None = None) -> None:
        self._messages: list[str] = [json.dumps(m) for m in (messages or [])]
        self._index = 0
        self._closed = False
        self._sent: list[str] = []

    async def send(self, data: str) -> None:
        self._sent.append(data)

    async def recv(self) -> str:
        if self._closed:
            raise ConnectionError("Connection closed")
        if self._index >= len(self._messages):
            # Block forever (simulating waiting for messages)
            await asyncio.sleep(3600)
            raise ConnectionError("Connection closed")
        msg = self._messages[self._index]
        self._index += 1
        return msg

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self._closed = True

    @property
    def sent_messages(self) -> list[dict[str, Any]]:
        """Return all sent messages as parsed dicts."""
        return [json.loads(s) for s in self._sent]

    def add_message(self, msg: dict[str, Any]) -> None:
        """Add a message to the queue."""
        self._messages.append(json.dumps(msg))


# ---------------------------------------------------------------------------
# Mock HTTP client for REST snapshot calls
# ---------------------------------------------------------------------------


class MockHTTPResponse:
    """Mock httpx.Response."""

    def __init__(
        self,
        status_code: int = 200,
        json_data: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self) -> dict[str, Any]:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


# ---------------------------------------------------------------------------
# Sample Binance messages
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_binance_ticker() -> dict[str, Any]:
    """Sample Binance 24hr ticker WebSocket message."""
    return {
        "e": "24hrTicker",
        "E": 1711000000000,
        "s": "BTCUSDT",
        "c": "67000.00",
        "b": "66999.50",
        "a": "67000.50",
        "v": "12345.67",
        "P": "2.35",
    }


@pytest.fixture
def sample_binance_trade() -> dict[str, Any]:
    """Sample Binance trade WebSocket message."""
    return {
        "e": "trade",
        "E": 1711000000000,
        "s": "BTCUSDT",
        "t": 123456789,
        "p": "67000.00",
        "q": "0.50",
        "m": False,
    }


@pytest.fixture
def sample_binance_kline() -> dict[str, Any]:
    """Sample Binance kline WebSocket message."""
    return {
        "e": "kline",
        "E": 1711000000000,
        "s": "BTCUSDT",
        "k": {
            "s": "BTCUSDT",
            "i": "1h",
            "o": "66800.00",
            "h": "67200.00",
            "l": "66700.00",
            "c": "67000.00",
            "v": "1234.56",
            "x": True,
        },
    }


@pytest.fixture
def sample_binance_depth_update() -> dict[str, Any]:
    """Sample Binance depthUpdate WebSocket message."""
    return {
        "e": "depthUpdate",
        "E": 1711000000000,
        "s": "BTCUSDT",
        "U": 100001,
        "u": 100002,
        "b": [["66999.00", "2.50"], ["66998.00", "1.00"]],
        "a": [["67001.00", "1.50"], ["67002.00", "3.00"]],
    }


@pytest.fixture
def sample_binance_depth_snapshot() -> dict[str, Any]:
    """Sample Binance REST depth snapshot response."""
    return {
        "lastUpdateId": 100000,
        "bids": [
            ["66999.00", "2.00"],
            ["66998.00", "1.50"],
            ["66997.00", "3.00"],
        ],
        "asks": [
            ["67001.00", "1.00"],
            ["67002.00", "3.00"],
            ["67003.00", "2.50"],
        ],
    }
