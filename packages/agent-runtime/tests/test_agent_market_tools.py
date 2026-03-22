"""Tests for market tools (MarketTickerTool, MarketKlineTool, MarketOrderbookTool)."""

from __future__ import annotations

from dataclasses import dataclass, field

from pnlclaw_agent.tools.market_tools import (
    MarketKlineTool,
    MarketOrderbookTool,
    MarketTickerTool,
)
from pnlclaw_types.market import (
    KlineEvent,
    OrderBookL2Snapshot,
    PriceLevel,
    TickerEvent,
)


# ---------------------------------------------------------------------------
# Mock MarketDataService
# ---------------------------------------------------------------------------


@dataclass
class MockMarketDataService:
    """Minimal mock returning fixed market data."""

    tickers: dict[str, TickerEvent] = field(default_factory=dict)
    klines: dict[str, KlineEvent] = field(default_factory=dict)
    orderbooks: dict[str, OrderBookL2Snapshot] = field(default_factory=dict)

    def get_ticker(self, symbol: str) -> TickerEvent | None:
        return self.tickers.get(symbol)

    def get_kline(self, symbol: str) -> KlineEvent | None:
        return self.klines.get(symbol)

    def get_orderbook(self, symbol: str) -> OrderBookL2Snapshot | None:
        return self.orderbooks.get(symbol)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = 1_700_000_000_000

_TICKER = TickerEvent(
    exchange="binance",
    symbol="BTC/USDT",
    timestamp=_NOW,
    last_price=67000.0,
    bid=66999.50,
    ask=67000.50,
    volume_24h=12345.67,
    change_24h_pct=2.35,
)

_KLINE = KlineEvent(
    exchange="binance",
    symbol="BTC/USDT",
    timestamp=_NOW,
    interval="1h",
    open=66800.0,
    high=67200.0,
    low=66700.0,
    close=67000.0,
    volume=500.0,
    closed=True,
)

_ORDERBOOK = OrderBookL2Snapshot(
    exchange="binance",
    symbol="BTC/USDT",
    timestamp=_NOW,
    sequence_id=100,
    bids=[
        PriceLevel(price=66999.0, quantity=1.5),
        PriceLevel(price=66998.0, quantity=2.0),
        PriceLevel(price=66997.0, quantity=3.0),
    ],
    asks=[
        PriceLevel(price=67001.0, quantity=1.0),
        PriceLevel(price=67002.0, quantity=2.5),
        PriceLevel(price=67003.0, quantity=1.8),
    ],
)


def _make_service(
    ticker: bool = True,
    kline: bool = True,
    orderbook: bool = True,
) -> MockMarketDataService:
    return MockMarketDataService(
        tickers={"BTC/USDT": _TICKER} if ticker else {},
        klines={"BTC/USDT": _KLINE} if kline else {},
        orderbooks={"BTC/USDT": _ORDERBOOK} if orderbook else {},
    )


# ---------------------------------------------------------------------------
# MarketTickerTool tests
# ---------------------------------------------------------------------------


class TestMarketTickerTool:
    def test_ticker_found(self) -> None:
        tool = MarketTickerTool(_make_service())
        result = tool.execute({"symbol": "BTC/USDT"})
        assert result.error is None
        assert "BTC/USDT" in result.output
        assert "67,000.00" in result.output
        assert "+2.35%" in result.output

    def test_ticker_not_found(self) -> None:
        tool = MarketTickerTool(_make_service(ticker=False))
        result = tool.execute({"symbol": "BTC/USDT"})
        assert "No ticker data available" in result.output

    def test_missing_symbol(self) -> None:
        tool = MarketTickerTool(_make_service())
        result = tool.execute({})
        assert result.error is not None
        assert "symbol" in result.error


# ---------------------------------------------------------------------------
# MarketKlineTool tests
# ---------------------------------------------------------------------------


class TestMarketKlineTool:
    def test_kline_found(self) -> None:
        tool = MarketKlineTool(_make_service())
        result = tool.execute({"symbol": "BTC/USDT"})
        assert result.error is None
        assert "BTC/USDT" in result.output
        assert "closed" in result.output
        assert "67,000.00" in result.output

    def test_kline_not_found(self) -> None:
        tool = MarketKlineTool(_make_service(kline=False))
        result = tool.execute({"symbol": "BTC/USDT"})
        assert "No kline data available" in result.output

    def test_missing_symbol(self) -> None:
        tool = MarketKlineTool(_make_service())
        result = tool.execute({})
        assert result.error is not None


# ---------------------------------------------------------------------------
# MarketOrderbookTool tests
# ---------------------------------------------------------------------------


class TestMarketOrderbookTool:
    def test_orderbook_found(self) -> None:
        tool = MarketOrderbookTool(_make_service())
        result = tool.execute({"symbol": "BTC/USDT"})
        assert result.error is None
        assert "BTC/USDT" in result.output
        assert "Asks:" in result.output
        assert "Bids:" in result.output
        assert "Spread" in result.output

    def test_orderbook_depth(self) -> None:
        tool = MarketOrderbookTool(_make_service())
        result = tool.execute({"symbol": "BTC/USDT", "depth": 2})
        # With depth=2, should only show 2 levels each side
        assert result.error is None
        bid_lines = [l for l in result.output.split("\n") if "66,997" in l]
        assert len(bid_lines) == 0  # 3rd bid level not shown

    def test_orderbook_not_found(self) -> None:
        tool = MarketOrderbookTool(_make_service(orderbook=False))
        result = tool.execute({"symbol": "BTC/USDT"})
        assert "No orderbook data available" in result.output

    def test_missing_symbol(self) -> None:
        tool = MarketOrderbookTool(_make_service())
        result = tool.execute({})
        assert result.error is not None
