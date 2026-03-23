"""Tests for market data endpoints (S3-L02)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from app.core.dependencies import get_market_service
from app.main import create_app
from httpx import ASGITransport, AsyncClient

from pnlclaw_types.market import KlineEvent, OrderBookL2Snapshot, PriceLevel, TickerEvent

# ---------------------------------------------------------------------------
# Stub MarketDataService
# ---------------------------------------------------------------------------


@dataclass
class StubMarketService:
    """Minimal stub matching MarketDataService interface."""

    _symbols: list[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    _tickers: dict[str, TickerEvent] = field(default_factory=dict)
    _klines: dict[str, KlineEvent] = field(default_factory=dict)
    _orderbooks: dict[str, OrderBookL2Snapshot] = field(default_factory=dict)

    def get_symbols(self) -> list[str]:
        return list(self._symbols)

    def get_ticker(self, symbol: str) -> TickerEvent | None:
        return self._tickers.get(symbol)

    def get_kline(self, symbol: str) -> KlineEvent | None:
        return self._klines.get(symbol)

    def get_orderbook(self, symbol: str) -> OrderBookL2Snapshot | None:
        return self._orderbooks.get(symbol)


def _make_stub() -> StubMarketService:
    stub = StubMarketService()
    stub._tickers["BTC/USDT"] = TickerEvent(
        exchange="binance",
        symbol="BTC/USDT",
        timestamp=1700000000000,
        last_price=67000.0,
        bid=66999.0,
        ask=67001.0,
        volume_24h=1000.0,
        change_24h_pct=1.5,
    )
    stub._klines["BTC/USDT"] = KlineEvent(
        exchange="binance",
        symbol="BTC/USDT",
        timestamp=1700000000000,
        interval="1h",
        open=66500.0,
        high=67200.0,
        low=66400.0,
        close=67000.0,
        volume=500.0,
        closed=True,
    )
    stub._orderbooks["BTC/USDT"] = OrderBookL2Snapshot(
        exchange="binance",
        symbol="BTC/USDT",
        timestamp=1700000000000,
        sequence_id=100,
        bids=[PriceLevel(price=66999.0 - i, quantity=1.0) for i in range(25)],
        asks=[PriceLevel(price=67001.0 + i, quantity=1.0) for i in range(25)],
    )
    return stub


def _make_app(svc: Any = None):
    app = create_app()
    if svc is not None:
        app.dependency_overrides[get_market_service] = lambda: svc
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_symbols():
    stub = _make_stub()
    app = _make_app(stub)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["data"]["symbols"]) == {"BTC/USDT", "ETH/USDT"}
    assert body["data"]["count"] == 2


@pytest.mark.asyncio
async def test_get_ticker():
    stub = _make_stub()
    app = _make_app(stub)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets/BTC-USDT/ticker")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["last_price"] == 67000.0
    assert body["data"]["symbol"] == "BTC/USDT"


@pytest.mark.asyncio
async def test_get_ticker_not_found():
    stub = _make_stub()
    app = _make_app(stub)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets/DOGE-USDT/ticker")
    # PnLClawError (NotFoundError) raised — returns 500 without error middleware,
    # 404 once S3-L07 error handler is installed.
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_get_kline():
    stub = _make_stub()
    app = _make_app(stub)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets/BTC-USDT/kline?interval=1h&limit=50")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["symbol"] == "BTC/USDT"
    assert len(body["data"]["klines"]) == 1
    assert body["data"]["klines"][0]["close"] == 67000.0


@pytest.mark.asyncio
async def test_get_orderbook():
    stub = _make_stub()
    app = _make_app(stub)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets/BTC-USDT/orderbook?depth=5")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]["bids"]) == 5
    assert len(body["data"]["asks"]) == 5


@pytest.mark.asyncio
async def test_market_service_unavailable():
    app = _make_app(None)  # no market service
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets")
    assert resp.status_code in (500, 503)
