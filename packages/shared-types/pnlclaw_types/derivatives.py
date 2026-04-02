"""Derivatives and tactical dashboard event models for PnLClaw.

Covers: liquidation events, funding rate, open interest, large trade
detection, and large order (whale wall) detection.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pnlclaw_types.common import Symbol, Timestamp
from pnlclaw_types.market import MarketType

# ---------------------------------------------------------------------------
# LiquidationEvent — single forced liquidation
# ---------------------------------------------------------------------------


class LiquidationEvent(BaseModel):
    """A single forced-liquidation order from an exchange."""

    exchange: str = Field(..., description="Exchange identifier")
    symbol: Symbol = Field(..., description="Normalized trading pair")
    market_type: MarketType = Field("futures", description="Always futures for liquidations")
    side: Literal["long", "short"] = Field(..., description="Which side was liquidated: long (SELL) or short (BUY)")
    quantity: float = Field(..., gt=0, description="Liquidation quantity in base currency")
    price: float = Field(..., gt=0, description="Liquidation order price")
    avg_price: float = Field(..., ge=0, description="Average fill price (0 if not filled yet)")
    notional_usd: float = Field(..., ge=0, description="Approximate notional value in USD")
    status: str = Field("FILLED", description="Order status: FILLED, NEW, etc.")
    timestamp: Timestamp = Field(..., description="Event time in millisecond epoch")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "exchange": "binance",
                    "symbol": "BTC/USDT",
                    "side": "long",
                    "quantity": 0.5,
                    "price": 68000.0,
                    "avg_price": 67950.0,
                    "notional_usd": 33975.0,
                    "status": "FILLED",
                    "timestamp": 1711000000000,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# LiquidationStats — aggregated liquidation statistics per time window
# ---------------------------------------------------------------------------


class LiquidationStats(BaseModel):
    """Aggregated liquidation statistics over a sliding time window."""

    symbol: str = Field("ALL", description="Symbol or 'ALL' for all-market aggregate")
    window: str = Field(..., description="Time window: 15m, 30m, 1h, 4h, 24h")
    long_liquidated_usd: float = Field(0.0, ge=0, description="Total long liquidation value (USD)")
    short_liquidated_usd: float = Field(0.0, ge=0, description="Total short liquidation value (USD)")
    total_liquidated_usd: float = Field(0.0, ge=0, description="Total liquidation value (USD)")
    long_count: int = Field(0, ge=0, description="Number of long liquidation events")
    short_count: int = Field(0, ge=0, description="Number of short liquidation events")
    largest_single_usd: float = Field(0.0, ge=0, description="Largest single liquidation in USD")
    timestamp: Timestamp = Field(..., description="Stats computation time")


# ---------------------------------------------------------------------------
# FundingRateEvent — from markPrice WS or REST polling
# ---------------------------------------------------------------------------


class FundingRateEvent(BaseModel):
    """Funding rate snapshot for a perpetual swap."""

    exchange: str = Field(..., description="Exchange identifier")
    symbol: Symbol = Field(..., description="Normalized trading pair")
    funding_rate: float = Field(..., description="Current funding rate (e.g. 0.0001 = 0.01%)")
    mark_price: float = Field(..., gt=0, description="Current mark price")
    index_price: float = Field(0.0, ge=0, description="Spot index price")
    next_funding_time: Timestamp = Field(0, description="Next funding settlement time (ms epoch)")
    timestamp: Timestamp = Field(..., description="Event time in millisecond epoch")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "exchange": "binance",
                    "symbol": "BTC/USDT",
                    "funding_rate": 0.0001,
                    "mark_price": 68000.0,
                    "index_price": 67990.0,
                    "next_funding_time": 1711036800000,
                    "timestamp": 1711000000000,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# OpenInterestSnapshot — from REST polling
# ---------------------------------------------------------------------------


class OpenInterestSnapshot(BaseModel):
    """Open interest snapshot for a futures/swap instrument."""

    exchange: str = Field(..., description="Exchange identifier")
    symbol: Symbol = Field(..., description="Normalized trading pair")
    open_interest: float = Field(..., ge=0, description="OI in contracts or base currency")
    open_interest_usd: float = Field(0.0, ge=0, description="OI in USD value")
    timestamp: Timestamp = Field(..., description="Snapshot time in millisecond epoch")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "exchange": "binance",
                    "symbol": "BTC/USDT",
                    "open_interest": 12345.67,
                    "open_interest_usd": 839506560.0,
                    "timestamp": 1711000000000,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# LargeTradeEvent — trade exceeding a configurable notional threshold
# ---------------------------------------------------------------------------


class LargeTradeEvent(BaseModel):
    """A trade that exceeded the large-trade notional threshold."""

    exchange: str = Field(..., description="Exchange identifier")
    symbol: Symbol = Field(..., description="Normalized trading pair")
    market_type: MarketType = Field("spot", description="Market type: spot or futures")
    side: Literal["buy", "sell"] = Field(..., description="Taker side")
    price: float = Field(..., gt=0, description="Trade price")
    quantity: float = Field(..., gt=0, description="Trade quantity in base currency")
    notional_usd: float = Field(..., gt=0, description="Notional value in USD")
    trade_id: str = Field("", description="Exchange-assigned trade/aggregate ID")
    timestamp: Timestamp = Field(..., description="Trade time in millisecond epoch")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "exchange": "binance",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "price": 68000.0,
                    "quantity": 2.5,
                    "notional_usd": 170000.0,
                    "trade_id": "123456789",
                    "timestamp": 1711000000000,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# LargeOrderEvent — single-level order book entry above threshold
# ---------------------------------------------------------------------------


class LargeOrderEvent(BaseModel):
    """A large resting order detected in the order book."""

    exchange: str = Field(..., description="Exchange identifier")
    symbol: Symbol = Field(..., description="Normalized trading pair")
    market_type: MarketType = Field("spot", description="Market type: spot or futures")
    side: Literal["bid", "ask"] = Field(..., description="Order book side")
    price: float = Field(..., gt=0, description="Price level")
    quantity: float = Field(..., gt=0, description="Quantity at this price level")
    notional_usd: float = Field(..., gt=0, description="Approximate notional value in USD")
    depth_rank: int = Field(0, ge=0, description="Rank in the book (0 = best)")
    event_type: Literal["appeared", "increased", "decreased", "disappeared"] = Field(
        "appeared", description="What happened to this large order"
    )
    timestamp: Timestamp = Field(..., description="Detection time in millisecond epoch")
