"""Trading data models for PnLClaw.

Covers order lifecycle, fills, positions, and PnL records.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from pnlclaw_types.common import Symbol, Timestamp


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OrderSide(str, Enum):
    """Direction of an order."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Supported order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    """Order lifecycle states.

    Transition: created → accepted → partial → filled
                                   ↘ cancelled
                        ↘ rejected
    """

    CREATED = "created"
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------


class Order(BaseModel):
    """A trading order with full lifecycle tracking."""

    id: str = Field(..., description="Unique order identifier")
    symbol: Symbol = Field(..., description="Normalized trading pair")
    side: OrderSide = Field(..., description="Buy or sell")
    type: OrderType = Field(..., description="Order type")
    status: OrderStatus = Field(
        OrderStatus.CREATED, description="Current order status"
    )
    quantity: float = Field(..., gt=0, description="Requested quantity in base currency")
    price: float | None = Field(
        None, ge=0, description="Limit price (None for market orders)"
    )
    stop_price: float | None = Field(
        None, ge=0, description="Stop trigger price (for stop orders)"
    )
    filled_quantity: float = Field(
        0.0, ge=0, description="Total quantity filled so far"
    )
    avg_fill_price: float | None = Field(
        None, ge=0, description="Volume-weighted average fill price"
    )
    created_at: Timestamp = Field(..., description="Order creation time (ms epoch)")
    updated_at: Timestamp = Field(..., description="Last update time (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "ord-001",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "type": "limit",
                    "status": "created",
                    "quantity": 0.5,
                    "price": 67000.0,
                    "stop_price": None,
                    "filled_quantity": 0.0,
                    "avg_fill_price": None,
                    "created_at": 1711000000000,
                    "updated_at": 1711000000000,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# Fill
# ---------------------------------------------------------------------------


class Fill(BaseModel):
    """A single fill (execution) against an order."""

    id: str = Field(..., description="Unique fill identifier")
    order_id: str = Field(..., description="Parent order ID")
    price: float = Field(..., gt=0, description="Execution price")
    quantity: float = Field(..., gt=0, description="Executed quantity")
    fee: float = Field(0.0, ge=0, description="Fee charged for this fill")
    fee_currency: str = Field("USDT", description="Currency of the fee")
    timestamp: Timestamp = Field(..., description="Fill time (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "fill-001",
                    "order_id": "ord-001",
                    "price": 67000.0,
                    "quantity": 0.25,
                    "fee": 0.01675,
                    "fee_currency": "USDT",
                    "timestamp": 1711000001000,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


class Position(BaseModel):
    """An open or closed trading position."""

    symbol: Symbol = Field(..., description="Normalized trading pair")
    side: OrderSide = Field(..., description="Position direction (buy=long, sell=short)")
    quantity: float = Field(..., ge=0, description="Current position size")
    avg_entry_price: float = Field(..., gt=0, description="Average entry price")
    unrealized_pnl: float = Field(0.0, description="Unrealized profit/loss")
    realized_pnl: float = Field(0.0, description="Realized profit/loss")
    opened_at: Timestamp = Field(..., description="Position open time (ms epoch)")
    updated_at: Timestamp = Field(..., description="Last update time (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "quantity": 0.5,
                    "avg_entry_price": 67000.0,
                    "unrealized_pnl": 150.0,
                    "realized_pnl": 0.0,
                    "opened_at": 1711000000000,
                    "updated_at": 1711000050000,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# PnLRecord
# ---------------------------------------------------------------------------


class PnLRecord(BaseModel):
    """Point-in-time PnL summary for a symbol."""

    symbol: Symbol = Field(..., description="Normalized trading pair")
    realized_pnl: float = Field(0.0, description="Realized profit/loss")
    unrealized_pnl: float = Field(0.0, description="Unrealized profit/loss")
    total_pnl: float = Field(0.0, description="Total PnL (realized + unrealized)")
    fees: float = Field(0.0, ge=0, description="Total fees paid")
    timestamp: Timestamp = Field(..., description="Record time (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "symbol": "BTC/USDT",
                    "realized_pnl": 200.0,
                    "unrealized_pnl": 150.0,
                    "total_pnl": 350.0,
                    "fees": 5.5,
                    "timestamp": 1711000060000,
                }
            ]
        }
    )
