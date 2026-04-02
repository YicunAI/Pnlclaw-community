"""OKX WebSocket message normalizer.

Converts raw OKX public-channel push data into unified PnLClaw market models.

OKX push format:
    {"arg":{"channel":"tickers","instId":"BTC-USDT"},"data":[{...}]}
    {"arg":{"channel":"candle1H","instId":"BTC-USDT"},"data":[[ts,o,h,l,c,vol,...]]}
"""

from __future__ import annotations

import time
from typing import Any

from pnlclaw_types.derivatives import FundingRateEvent, LiquidationEvent
from pnlclaw_types.market import (
    KlineEvent,
    OrderBookL2Snapshot,
    PriceLevel,
    TickerEvent,
    TradeEvent,
)

EXCHANGE = "okx"

# OKX candle channels to PnLClaw interval string
_CANDLE_INTERVAL_MAP: dict[str, str] = {
    "candle1s": "1s",
    "candle1m": "1m",
    "candle3m": "3m",
    "candle5m": "5m",
    "candle15m": "15m",
    "candle30m": "30m",
    "candle1H": "1h",
    "candle2H": "2h",
    "candle4H": "4h",
    "candle6H": "6h",
    "candle12H": "12h",
    "candle1D": "1d",
    "candle1W": "1w",
    "candle1M": "1M",
}


def _okx_symbol_to_unified(inst_id: str) -> str:
    """Convert OKX instId to unified format ``BTC/USDT``.

    Handles both spot (``BTC-USDT``) and swap (``BTC-USDT-SWAP``) instIds.
    Product suffixes are stripped so the unified symbol is always ``BASE/QUOTE``.
    """
    upper = inst_id.upper()
    for suffix in ("-SWAP", "-FUTURES"):
        if upper.endswith(suffix):
            upper = upper[: -len(suffix)]
            break
    parts = upper.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return upper


class OKXNormalizer:
    """Normalize OKX WebSocket push data into unified event models."""

    def normalize_ticker(self, data: dict[str, Any], inst_id: str) -> TickerEvent:
        """Normalize an OKX ticker push data item."""
        change_pct = 0.0
        open24h = float(data.get("open24h", 0) or 0)
        last = float(data["last"])
        if open24h > 0:
            change_pct = ((last - open24h) / open24h) * 100

        return TickerEvent(
            exchange=EXCHANGE,
            symbol=_okx_symbol_to_unified(inst_id),
            timestamp=int(data["ts"]),
            last_price=last,
            bid=float(data.get("bidPx", 0) or 0),
            ask=float(data.get("askPx", 0) or 0),
            volume_24h=float(data.get("vol24h", 0) or 0),
            quote_volume_24h=float(data.get("volCcy24h", 0) or 0),
            high_24h=float(data.get("high24h", 0) or 0),
            low_24h=float(data.get("low24h", 0) or 0),
            change_24h_pct=round(change_pct, 4),
        )

    def normalize_candle(self, candle: list[str], inst_id: str, channel: str) -> KlineEvent:
        """Normalize an OKX candlestick push data item.

        OKX candle array: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        """
        interval = _CANDLE_INTERVAL_MAP.get(channel, "1h")
        return KlineEvent(
            exchange=EXCHANGE,
            symbol=_okx_symbol_to_unified(inst_id),
            timestamp=int(candle[0]),
            interval=interval,
            open=float(candle[1]),
            high=float(candle[2]),
            low=float(candle[3]),
            close=float(candle[4]),
            volume=float(candle[5]),
            closed=candle[8] == "1" if len(candle) > 8 else False,
        )

    def normalize_trade(self, data: dict[str, Any], inst_id: str) -> TradeEvent:
        """Normalize an OKX trades channel push item.

        OKX trade fields: tradeId, px, sz, side, ts
        """
        return TradeEvent(
            exchange=EXCHANGE,
            symbol=_okx_symbol_to_unified(inst_id),
            timestamp=int(data["ts"]),
            trade_id=str(data["tradeId"]),
            price=float(data["px"]),
            quantity=float(data["sz"]),
            side=data["side"],
        )

    def normalize_liquidation(self, data: dict[str, Any], inst_id: str) -> list[LiquidationEvent]:
        """Normalize an OKX liquidation-orders channel push.

        OKX pushes ``details`` array inside each item, each detail being
        one liquidation event with bkPx (bankruptcy price), sz, side, ts.
        """
        results: list[LiquidationEvent] = []
        symbol = _okx_symbol_to_unified(inst_id)
        for detail in data.get("details", []):
            raw_side = detail.get("side", "sell")
            side = "long" if raw_side == "sell" else "short"
            qty = float(detail.get("sz", 0))
            price = float(detail.get("bkPx", 0))
            notional = qty * price
            results.append(
                LiquidationEvent(
                    exchange=EXCHANGE,
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    price=price,
                    avg_price=price,
                    notional_usd=notional,
                    status="FILLED",
                    timestamp=int(detail.get("ts", 0)),
                )
            )
        return results

    def normalize_funding_rate(self, data: dict[str, Any], inst_id: str) -> FundingRateEvent:
        """Normalize an OKX funding rate REST response item."""
        return FundingRateEvent(
            exchange=EXCHANGE,
            symbol=_okx_symbol_to_unified(inst_id),
            funding_rate=float(data.get("fundingRate", 0) or 0),
            mark_price=float(data.get("markPx", 0) or 0) if data.get("markPx") else 0.0,
            index_price=0.0,
            next_funding_time=int(data.get("nextFundingTime", 0) or 0),
            timestamp=int(data.get("fundingTime", 0) or data.get("ts", 0) or 0),
        )

    def normalize_orderbook(self, data: dict[str, Any], inst_id: str) -> OrderBookL2Snapshot:
        """Normalize an OKX books5 push data item.

        OKX books5 levels: ``[[price, size, deprecated, numOrders], ...]``
        """
        ts_raw = data.get("ts")
        ts = int(ts_raw) if ts_raw else int(time.time() * 1000)

        def _parse_levels(raw: list[list[str]]) -> list[PriceLevel]:
            return [PriceLevel(price=float(lv[0]), quantity=float(lv[1])) for lv in raw if len(lv) >= 2]

        return OrderBookL2Snapshot(
            exchange=EXCHANGE,
            symbol=_okx_symbol_to_unified(inst_id),
            timestamp=ts,
            sequence_id=ts,
            bids=_parse_levels(data.get("bids", [])),
            asks=_parse_levels(data.get("asks", [])),
        )
