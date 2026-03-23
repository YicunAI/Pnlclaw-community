"""OKX WebSocket message normalizer.

Converts raw OKX public-channel push data into unified PnLClaw market models.

OKX push format:
    {"arg":{"channel":"tickers","instId":"BTC-USDT"},"data":[{...}]}
    {"arg":{"channel":"candle1H","instId":"BTC-USDT"},"data":[[ts,o,h,l,c,vol,...]]}
"""

from __future__ import annotations

from typing import Any

from pnlclaw_types.market import KlineEvent, TickerEvent

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
    """Convert OKX instId (e.g. ``BTC-USDT``) to unified format ``BTC/USDT``."""
    return inst_id.replace("-", "/")


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
            change_24h_pct=round(change_pct, 4),
        )

    def normalize_candle(
        self, candle: list[str], inst_id: str, channel: str
    ) -> KlineEvent:
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
