"""Market data tools — ticker, kline, and orderbook queries.

Each tool wraps a ``MarketDataService`` method and formats the result
as LLM-readable text.
"""

from __future__ import annotations

from typing import Any

from pnlclaw_agent.tools.base import BaseTool, ToolResult
from pnlclaw_types.risk import RiskLevel

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_price(value: float) -> str:
    """Format a price with up to 8 significant decimals."""
    if value >= 1.0:
        return f"{value:,.2f}"
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _fmt_qty(value: float) -> str:
    """Format a quantity."""
    if value >= 1.0:
        return f"{value:,.4f}"
    return f"{value:.8f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# MarketTickerTool
# ---------------------------------------------------------------------------


class MarketTickerTool(BaseTool):
    """Fetch the latest ticker snapshot for a trading pair."""

    def __init__(self, market_service: Any) -> None:
        self._service = market_service

    @property
    def name(self) -> str:
        return "market_ticker"

    @property
    def description(self) -> str:
        return (
            "Get the latest ticker for a trading pair, including last price, "
            "bid/ask, 24h volume, and 24h price change."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair, e.g. 'BTC/USDT'",
                },
            },
            "required": ["symbol"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        symbol = args.get("symbol", "")
        if not symbol:
            return ToolResult(output="", error="Missing required parameter: symbol")

        ticker = self._service.get_ticker(symbol)
        if ticker is None:
            return ToolResult(output=f"No ticker data available for {symbol}")

        lines = [
            f"{ticker.symbol} Ticker ({ticker.exchange})",
            f"  Last: {_fmt_price(ticker.last_price)}",
            f"  Bid: {_fmt_price(ticker.bid)} | Ask: {_fmt_price(ticker.ask)}",
            f"  24h Volume: {_fmt_qty(ticker.volume_24h)}",
            f"  24h Change: {ticker.change_24h_pct:+.2f}%",
        ]
        return ToolResult(output="\n".join(lines))


# ---------------------------------------------------------------------------
# MarketKlineTool
# ---------------------------------------------------------------------------


class MarketKlineTool(BaseTool):
    """Fetch the latest candlestick (kline) for a trading pair."""

    def __init__(self, market_service: Any) -> None:
        self._service = market_service

    @property
    def name(self) -> str:
        return "market_kline"

    @property
    def description(self) -> str:
        return (
            "Get the latest candlestick (OHLCV) for a trading pair, "
            "including open, high, low, close, and volume."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair, e.g. 'BTC/USDT'",
                },
            },
            "required": ["symbol"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        symbol = args.get("symbol", "")
        if not symbol:
            return ToolResult(output="", error="Missing required parameter: symbol")

        kline = self._service.get_kline(symbol)
        if kline is None:
            return ToolResult(output=f"No kline data available for {symbol}")

        status = "closed" if kline.closed else "open"
        lines = [
            f"{kline.symbol} Kline ({kline.exchange}, {kline.interval}, {status})",
            f"  Open: {_fmt_price(kline.open)} | High: {_fmt_price(kline.high)}",
            f"  Low: {_fmt_price(kline.low)} | Close: {_fmt_price(kline.close)}",
            f"  Volume: {_fmt_qty(kline.volume)}",
        ]
        return ToolResult(output="\n".join(lines))


# ---------------------------------------------------------------------------
# MarketOrderbookTool
# ---------------------------------------------------------------------------


class MarketOrderbookTool(BaseTool):
    """Fetch the current L2 order book snapshot for a trading pair."""

    def __init__(self, market_service: Any) -> None:
        self._service = market_service

    @property
    def name(self) -> str:
        return "market_orderbook"

    @property
    def description(self) -> str:
        return (
            "Get the current L2 order book for a trading pair, showing "
            "the top bid and ask levels with price and quantity."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair, e.g. 'BTC/USDT'",
                },
                "depth": {
                    "type": "integer",
                    "description": "Number of levels to show (default 10)",
                },
            },
            "required": ["symbol"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        symbol = args.get("symbol", "")
        if not symbol:
            return ToolResult(output="", error="Missing required parameter: symbol")

        book = self._service.get_orderbook(symbol)
        if book is None:
            return ToolResult(output=f"No orderbook data available for {symbol}")

        depth = args.get("depth", 10)
        bids = book.bids[:depth]
        asks = book.asks[:depth]

        lines = [f"{book.symbol} Order Book ({book.exchange})", ""]

        # Asks (reversed so lowest ask is at bottom, closest to spread)
        lines.append("  Asks:")
        for level in reversed(asks):
            lines.append(f"    {_fmt_price(level.price):>14}  |  {_fmt_qty(level.quantity)}")

        # Spread
        if bids and asks:
            spread = asks[0].price - bids[0].price
            lines.append(f"  --- Spread: {_fmt_price(spread)} ---")

        # Bids
        lines.append("  Bids:")
        for level in bids:
            lines.append(f"    {_fmt_price(level.price):>14}  |  {_fmt_qty(level.quantity)}")

        return ToolResult(output="\n".join(lines))
