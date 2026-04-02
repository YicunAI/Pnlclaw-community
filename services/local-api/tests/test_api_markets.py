"""Tests for market data endpoints (S3-L02)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from app.core.dependencies import get_market_service, get_settings_service
from app.core.settings_service import SettingsService
from app.main import create_app
from httpx import ASGITransport, AsyncClient

from pnlclaw_types.market import KlineEvent, OrderBookL2Snapshot, PriceLevel, TickerEvent

# ---------------------------------------------------------------------------
# Stub MarketDataService (multi-source interface)
# ---------------------------------------------------------------------------


@dataclass
class _StubSource:
    """Stub for a single (exchange, market_type) source."""

    symbols: list[str] = field(default_factory=list)
    tickers: dict[str, TickerEvent] = field(default_factory=dict)
    klines: dict[str, KlineEvent] = field(default_factory=dict)
    orderbooks: dict[str, OrderBookL2Snapshot] = field(default_factory=dict)

    def get_symbols(self) -> list[str]:
        return list(self.symbols)

    def get_ticker(self, symbol: str) -> TickerEvent | None:
        return self.tickers.get(symbol)

    def get_kline(self, symbol: str) -> KlineEvent | None:
        return self.klines.get(symbol)

    def get_orderbook(self, symbol: str) -> OrderBookL2Snapshot | None:
        return self.orderbooks.get(symbol)

    async def subscribe(self, symbol: str, **kwargs: Any) -> None:
        if symbol not in self.symbols:
            self.symbols.append(symbol)


@dataclass
class StubMarketService:
    """Minimal stub matching the new multi-source MarketDataService interface."""

    _sources: dict[tuple[str, str], _StubSource] = field(default_factory=dict)

    def get_source(self, exchange: str = "binance", market_type: str = "spot") -> _StubSource | None:
        return self._sources.get((exchange, market_type))

    def get_symbols(self, exchange: str = "binance", market_type: str = "spot") -> list[str]:
        src = self._sources.get((exchange, market_type))
        return src.get_symbols() if src else []

    def get_ticker(self, symbol: str, exchange: str = "binance", market_type: str = "spot") -> TickerEvent | None:
        src = self._sources.get((exchange, market_type))
        return src.get_ticker(symbol) if src else None

    def get_kline(self, symbol: str, exchange: str = "binance", market_type: str = "spot") -> KlineEvent | None:
        src = self._sources.get((exchange, market_type))
        return src.get_kline(symbol) if src else None

    def get_orderbook(
        self, symbol: str, exchange: str = "binance", market_type: str = "spot"
    ) -> OrderBookL2Snapshot | None:
        src = self._sources.get((exchange, market_type))
        return src.get_orderbook(symbol) if src else None

    async def add_symbol(self, symbol: str, *, exchange: str = "binance", market_type: str = "spot", **kw: Any) -> None:
        src = self._sources.get((exchange, market_type))
        if src:
            await src.subscribe(symbol)

    async def fetch_klines_rest(
        self,
        symbol: str,
        exchange: str = "binance",
        market_type: str = "spot",
        *,
        interval: str = "1h",
        limit: int = 100,
        end_time: int | None = None,
    ) -> list[KlineEvent]:
        src = self._sources.get((exchange, market_type))
        if src is None:
            return []
        kline = src.get_kline(symbol)
        return [kline] if kline else []


def _make_stub() -> StubMarketService:
    source = _StubSource(
        symbols=["BTC/USDT", "ETH/USDT"],
        tickers={
            "BTC/USDT": TickerEvent(
                exchange="binance",
                market_type="spot",
                symbol="BTC/USDT",
                timestamp=1700000000000,
                last_price=67000.0,
                bid=66999.0,
                ask=67001.0,
                volume_24h=1000.0,
                change_24h_pct=1.5,
            ),
        },
        klines={
            "BTC/USDT": KlineEvent(
                exchange="binance",
                market_type="spot",
                symbol="BTC/USDT",
                timestamp=1700000000000,
                interval="1h",
                open=66500.0,
                high=67200.0,
                low=66400.0,
                close=67000.0,
                volume=500.0,
                closed=True,
            ),
        },
        orderbooks={
            "BTC/USDT": OrderBookL2Snapshot(
                exchange="binance",
                market_type="spot",
                symbol="BTC/USDT",
                timestamp=1700000000000,
                sequence_id=100,
                bids=[PriceLevel(price=66999.0 - i, quantity=1.0) for i in range(25)],
                asks=[PriceLevel(price=67001.0 + i, quantity=1.0) for i in range(25)],
            ),
        },
    )
    stub = StubMarketService(_sources={("binance", "spot"): source})
    return stub


class StubSecretManager:
    def keyring_available(self) -> bool:
        return True

    async def exists(self, ref: Any) -> bool:
        return False

    async def store(self, ref: Any, value: str) -> None:
        return None

    async def delete(self, ref: Any) -> None:
        return None


def _make_app(svc: Any = None):
    app = create_app()
    if svc is not None:
        app.dependency_overrides[get_market_service] = lambda: svc
    settings_service = SettingsService(secret_manager=StubSecretManager())
    app.dependency_overrides[get_settings_service] = lambda: settings_service
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
async def test_get_ticker_with_supported_source_query():
    stub = _make_stub()
    app = _make_app(stub)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets/BTC-USDT/ticker?exchange=binance&market_type=spot")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_ticker_invalid_source_query_returns_400():
    stub = _make_stub()
    app = _make_app(stub)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets/BTC-USDT/ticker?exchange=bybit&market_type=spot")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETER"


@pytest.mark.asyncio
async def test_get_ticker_unavailable_source_returns_503():
    stub = _make_stub()
    app = _make_app(stub)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets/BTC-USDT/ticker?exchange=okx&market_type=futures")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_get_ticker_not_found():
    stub = _make_stub()
    app = _make_app(stub)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets/DOGE-USDT/ticker")
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
    app = _make_app(None)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets")
    assert resp.status_code in (500, 503)


@pytest.mark.asyncio
async def test_kline_response_includes_exchange_and_market_type():
    stub = _make_stub()
    app = _make_app(stub)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets/BTC-USDT/kline?interval=1h&exchange=binance&market_type=spot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["exchange"] == "binance"
    assert body["data"]["market_type"] == "spot"


@pytest.mark.asyncio
async def test_list_symbols_response_includes_exchange_and_market_type():
    stub = _make_stub()
    app = _make_app(stub)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets?exchange=binance&market_type=spot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["exchange"] == "binance"
    assert body["data"]["market_type"] == "spot"
