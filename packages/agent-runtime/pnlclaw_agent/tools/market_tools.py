"""Market data tools — ticker, kline, and orderbook queries.

Each tool wraps a ``MarketDataService`` method and formats the result
as LLM-readable text.  All tools accept optional ``exchange`` and
``market_type`` parameters so the agent can query any registered source.
"""

from __future__ import annotations

from typing import Any

from pnlclaw_agent.tools.base import BaseTool, ToolResult
from pnlclaw_types.risk import RiskLevel

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_EXCHANGE_PARAM: dict[str, Any] = {
    "type": "string",
    "description": "Exchange to query, e.g. 'binance', 'okx'. Uses the user's current exchange if omitted.",
}

_MARKET_TYPE_PARAM: dict[str, Any] = {
    "type": "string",
    "description": "Market type: 'spot' or 'futures'. Uses the user's current market type if omitted.",
}


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


def _route_kwargs(args: dict[str, Any]) -> dict[str, str]:
    """Extract exchange/market_type routing kwargs from tool arguments."""
    kwargs: dict[str, str] = {}
    exchange = args.get("exchange")
    market_type = args.get("market_type")
    if exchange:
        kwargs["exchange"] = exchange
    if market_type:
        kwargs["market_type"] = market_type
    return kwargs


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
            "Get the latest ticker for a trading pair on a specific exchange, "
            "including last price, bid/ask, 24h volume, and 24h price change."
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
                "exchange": _EXCHANGE_PARAM,
                "market_type": _MARKET_TYPE_PARAM,
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

        ticker = self._service.get_ticker(symbol, **_route_kwargs(args))
        if ticker is None:
            exchange = args.get("exchange", "default")
            return ToolResult(output=f"No ticker data available for {symbol} on {exchange}")

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
    """Fetch candlestick (kline) data for a trading pair via REST API."""

    def __init__(self, market_service: Any) -> None:
        self._service = market_service

    @property
    def name(self) -> str:
        return "market_kline"

    @property
    def description(self) -> str:
        return (
            "Get recent candlesticks (OHLCV) for a trading pair on a specific exchange. "
            "Supports any interval: '1m', '5m', '15m', '30m', '1h', '4h', '1d'. "
            "Returns the most recent candles with open, high, low, close, and volume."
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
                "interval": {
                    "type": "string",
                    "description": "Kline interval: '1m', '5m', '15m', '30m', '1h', '4h', '1d'. Uses the user's current timeframe if omitted.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of candles to return (default 50, max 1500). Use 200+ for multi-week analysis, 500+ for multi-month. The tool auto-paginates.",
                },
                "exchange": _EXCHANGE_PARAM,
                "market_type": _MARKET_TYPE_PARAM,
            },
            "required": ["symbol"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        """Sync fallback — returns the cached WS kline."""
        symbol = args.get("symbol", "")
        if not symbol:
            return ToolResult(output="", error="Missing required parameter: symbol")

        route = _route_kwargs(args)
        kline = self._service.get_kline(symbol, **route)
        if kline is None:
            return ToolResult(output=f"No kline data available for {symbol}")

        return ToolResult(output=_format_single_kline(kline))

    async def async_execute(self, args: dict[str, Any]) -> ToolResult | None:
        """Async path — fetches klines via REST with auto-pagination."""
        symbol = args.get("symbol", "")
        if not symbol:
            return ToolResult(output="", error="Missing required parameter: symbol")

        interval = args.get("interval", "1h")
        limit = min(args.get("limit", 50), 1500)
        route = _route_kwargs(args)

        if limit > 200 and hasattr(self._service, "fetch_klines_batch"):
            try:
                klines = await self._service.fetch_klines_batch(
                    symbol,
                    interval=interval,
                    total=limit,
                    **route,
                )
            except Exception:
                klines = []
        elif hasattr(self._service, "fetch_klines_rest"):
            try:
                klines = await self._service.fetch_klines_rest(
                    symbol,
                    interval=interval,
                    limit=limit,
                    **route,
                )
            except Exception:
                return None
        else:
            return None

        if not klines:
            return ToolResult(output=f"No {interval} kline data for {symbol}")

        display_klines = klines
        summarize = len(klines) > 100
        if summarize:
            head = klines[:20]
            tail = klines[-30:]
            display_klines = head + tail

        lines = [
            f"{symbol} Klines ({klines[0].exchange if klines else '?'}, {interval}, {len(klines)} candles fetched)",
            "",
        ]

        import datetime

        if summarize:
            lines.append(f"  (Showing first 20 + last 30 of {len(klines)} candles)")
            lines.append("")

        shown_count = 0
        for i, k in enumerate(display_klines):
            status = "C" if k.closed else "O"
            ts_label = ""
            if hasattr(k, "timestamp") and k.timestamp:
                dt = datetime.datetime.fromtimestamp(k.timestamp / 1000, tz=datetime.UTC)
                ts_label = dt.strftime("%m-%d %H:%M") + " "
            lines.append(
                f"  {ts_label}[{status}] O:{_fmt_price(k.open)} H:{_fmt_price(k.high)} "
                f"L:{_fmt_price(k.low)} C:{_fmt_price(k.close)} V:{_fmt_qty(k.volume)}"
            )
            shown_count += 1
            if summarize and i == len(head) - 1:
                lines.append(f"  ... ({len(klines) - 50} candles omitted) ...")

        highs = [k.high for k in klines]
        lows = [k.low for k in klines]
        volumes = [k.volume for k in klines]
        latest = klines[-1]

        lines.append("")
        lines.append("  === Summary Statistics ===")
        lines.append(f"  Period high: {_fmt_price(max(highs))} | Period low: {_fmt_price(min(lows))}")
        lines.append(f"  Latest close: {_fmt_price(latest.close)}")
        if len(klines) >= 2:
            first_open = klines[0].open
            if first_open > 0:
                total_change = ((latest.close - first_open) / first_open) * 100
                lines.append(f"  Period change: {total_change:+.2f}%")
        lines.append(f"  Avg volume: {_fmt_qty(sum(volumes) / len(volumes))}")
        lines.append(f"  Total candles: {len(klines)}")

        return ToolResult(output="\n".join(lines))


def _format_single_kline(kline: Any) -> str:
    """Format a single kline event for LLM consumption."""
    status = "closed" if kline.closed else "open"
    return "\n".join(
        [
            f"{kline.symbol} Kline ({kline.exchange}, {kline.interval}, {status})",
            f"  Open: {_fmt_price(kline.open)} | High: {_fmt_price(kline.high)}",
            f"  Low: {_fmt_price(kline.low)} | Close: {_fmt_price(kline.close)}",
            f"  Volume: {_fmt_qty(kline.volume)}",
        ]
    )


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
            "Get the current L2 order book for a trading pair on a specific exchange, "
            "showing the top bid and ask levels with price and quantity."
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
                "exchange": _EXCHANGE_PARAM,
                "market_type": _MARKET_TYPE_PARAM,
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

        book = self._service.get_orderbook(symbol, **_route_kwargs(args))
        if book is None:
            exchange = args.get("exchange", "default")
            return ToolResult(output=f"No orderbook data available for {symbol} on {exchange}")

        depth = args.get("depth", 10)
        bids = book.bids[:depth]
        asks = book.asks[:depth]

        lines = [f"{book.symbol} Order Book ({book.exchange})", ""]

        lines.append("  Asks:")
        for level in reversed(asks):
            lines.append(f"    {_fmt_price(level.price):>14}  |  {_fmt_qty(level.quantity)}")

        if bids and asks:
            spread = asks[0].price - bids[0].price
            spread_pct = (spread / asks[0].price) * 100 if asks[0].price > 0 else 0
            lines.append(f"  --- Spread: {_fmt_price(spread)} ({spread_pct:.4f}%) ---")

        lines.append("  Bids:")
        for level in bids:
            lines.append(f"    {_fmt_price(level.price):>14}  |  {_fmt_qty(level.quantity)}")

        return ToolResult(output="\n".join(lines))
