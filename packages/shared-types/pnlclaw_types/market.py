"""Market data event models for PnLClaw.

All market events carry ``exchange``, ``symbol``, and ``timestamp`` standard fields.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pnlclaw_types.common import Symbol, Timestamp

# ---------------------------------------------------------------------------
# PriceLevel — helper for order book entries
# ---------------------------------------------------------------------------


class PriceLevel(BaseModel):
    """Single price level in an order book (bid or ask)."""

    price: float = Field(..., gt=0, description="Price at this level")
    quantity: float = Field(..., ge=0, description="Quantity available at this price")

    model_config = ConfigDict(json_schema_extra={"examples": [{"price": 67000.0, "quantity": 1.5}]})


# ---------------------------------------------------------------------------
# TickerEvent
# ---------------------------------------------------------------------------


class TickerEvent(BaseModel):
    """Real-time ticker snapshot from an exchange."""

    exchange: str = Field(..., description="Exchange identifier, e.g. 'binance'")
    symbol: Symbol = Field(..., description="Normalized trading pair, e.g. 'BTC/USDT'")
    timestamp: Timestamp = Field(..., description="Event time in millisecond epoch")
    last_price: float = Field(..., gt=0, description="Last traded price")
    bid: float = Field(..., ge=0, description="Best bid price")
    ask: float = Field(..., ge=0, description="Best ask price")
    volume_24h: float = Field(..., ge=0, description="24-hour trading volume in base currency")
    change_24h_pct: float = Field(..., description="24-hour price change percentage")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "exchange": "binance",
                    "symbol": "BTC/USDT",
                    "timestamp": 1711000000000,
                    "last_price": 67000.0,
                    "bid": 66999.5,
                    "ask": 67000.5,
                    "volume_24h": 12345.67,
                    "change_24h_pct": 2.35,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# TradeEvent
# ---------------------------------------------------------------------------


class TradeEvent(BaseModel):
    """Individual trade (tick) from an exchange."""

    exchange: str = Field(..., description="Exchange identifier")
    symbol: Symbol = Field(..., description="Normalized trading pair")
    timestamp: Timestamp = Field(..., description="Trade time in millisecond epoch")
    trade_id: str = Field(..., description="Exchange-assigned trade ID")
    price: float = Field(..., gt=0, description="Trade price")
    quantity: float = Field(..., gt=0, description="Trade quantity in base currency")
    side: str = Field(..., description="Taker side: 'buy' or 'sell'")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "exchange": "binance",
                    "symbol": "BTC/USDT",
                    "timestamp": 1711000000000,
                    "trade_id": "123456789",
                    "price": 67000.0,
                    "quantity": 0.5,
                    "side": "buy",
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# KlineEvent
# ---------------------------------------------------------------------------


class KlineEvent(BaseModel):
    """Candlestick / K-line data point."""

    exchange: str = Field(..., description="Exchange identifier")
    symbol: Symbol = Field(..., description="Normalized trading pair")
    timestamp: Timestamp = Field(..., description="Kline open time in millisecond epoch")
    interval: str = Field(..., description="Kline interval, e.g. '1m', '1h', '1d'")
    open: float = Field(..., gt=0, description="Open price")
    high: float = Field(..., gt=0, description="High price")
    low: float = Field(..., gt=0, description="Low price")
    close: float = Field(..., gt=0, description="Close price")
    volume: float = Field(..., ge=0, description="Volume in base currency")
    closed: bool = Field(..., description="Whether this kline is finalized")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "exchange": "binance",
                    "symbol": "BTC/USDT",
                    "timestamp": 1711000000000,
                    "interval": "1h",
                    "open": 66800.0,
                    "high": 67200.0,
                    "low": 66700.0,
                    "close": 67000.0,
                    "volume": 1234.56,
                    "closed": True,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# OrderBookL2Snapshot
# ---------------------------------------------------------------------------


class OrderBookL2Snapshot(BaseModel):
    """Full L2 order book snapshot."""

    exchange: str = Field(..., description="Exchange identifier")
    symbol: Symbol = Field(..., description="Normalized trading pair")
    timestamp: Timestamp = Field(..., description="Snapshot time in millisecond epoch")
    sequence_id: int = Field(..., description="Sequence number for ordering / gap detection")
    bids: list[PriceLevel] = Field(
        default_factory=list, description="Bid levels sorted by price descending"
    )
    asks: list[PriceLevel] = Field(
        default_factory=list, description="Ask levels sorted by price ascending"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "exchange": "binance",
                    "symbol": "BTC/USDT",
                    "timestamp": 1711000000000,
                    "sequence_id": 100001,
                    "bids": [
                        {"price": 66999.0, "quantity": 2.0},
                        {"price": 66998.0, "quantity": 1.5},
                    ],
                    "asks": [
                        {"price": 67001.0, "quantity": 1.0},
                        {"price": 67002.0, "quantity": 3.0},
                    ],
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# OrderBookL2Delta
# ---------------------------------------------------------------------------


class OrderBookL2Delta(BaseModel):
    """Incremental L2 order book update (delta)."""

    exchange: str = Field(..., description="Exchange identifier")
    symbol: Symbol = Field(..., description="Normalized trading pair")
    timestamp: Timestamp = Field(..., description="Delta time in millisecond epoch")
    sequence_id: int = Field(..., description="Sequence number for ordering / gap detection")
    bids: list[PriceLevel] = Field(
        default_factory=list, description="Updated bid levels (quantity=0 means remove)"
    )
    asks: list[PriceLevel] = Field(
        default_factory=list, description="Updated ask levels (quantity=0 means remove)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "exchange": "binance",
                    "symbol": "BTC/USDT",
                    "timestamp": 1711000000001,
                    "sequence_id": 100002,
                    "bids": [{"price": 66999.0, "quantity": 2.5}],
                    "asks": [{"price": 67001.0, "quantity": 0.0}],
                }
            ]
        }
    )
