"""Trading data models for PnLClaw.

Covers order lifecycle, fills, positions, PnL records,
exchange-originated private events, and execution mode.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pnlclaw_types.common import Symbol, Timestamp

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExecutionMode(str, Enum):
    """Trading execution mode."""

    PAPER = "paper"
    LIVE = "live"


class OrderSide(str, Enum):
    """Direction of an order."""

    BUY = "buy"
    SELL = "sell"


class MarginMode(str, Enum):
    """Margin mode for derivatives trading (mirrors OKX tdMode)."""

    CROSS = "cross"
    ISOLATED = "isolated"
    CASH = "cash"


class PositionSide(str, Enum):
    """Position side for dual-position mode (mirrors OKX posSide)."""

    LONG = "long"
    SHORT = "short"
    NET = "net"


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
    """A trading order with full lifecycle tracking.

    Supports both spot (cash) and derivatives (cross/isolated margin) modes,
    mirroring OKX's ``/api/v5/trade/order`` contract.
    """

    id: str = Field(..., description="Unique order identifier")
    symbol: Symbol = Field(..., description="Normalized trading pair, e.g. BTC-USDT-SWAP")
    side: OrderSide = Field(..., description="Buy or sell")
    type: OrderType = Field(..., description="Order type")
    status: OrderStatus = Field(OrderStatus.CREATED, description="Current order status")
    quantity: float = Field(..., gt=0, description="Order size in quote currency (USDT)")
    price: float | None = Field(None, ge=0, description="Limit price (None for market orders)")
    stop_price: float | None = Field(None, ge=0, description="Stop trigger price")
    filled_quantity: float = Field(0.0, ge=0, description="Total quantity filled so far (USDT)")
    avg_fill_price: float | None = Field(None, ge=0, description="Volume-weighted average fill price")
    leverage: int = Field(1, ge=1, le=125, description="Leverage multiplier")
    margin_mode: MarginMode = Field(MarginMode.CROSS, description="Margin mode: cross/isolated/cash")
    pos_side: PositionSide = Field(PositionSide.NET, description="Position side: long/short/net")
    reduce_only: bool = Field(False, description="Close position only")
    created_at: Timestamp = Field(..., description="Order creation time (ms epoch)")
    updated_at: Timestamp = Field(..., description="Last update time (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "ord-001",
                    "symbol": "BTC-USDT-SWAP",
                    "side": "buy",
                    "type": "limit",
                    "status": "created",
                    "quantity": 100.0,
                    "price": 67000.0,
                    "stop_price": None,
                    "filled_quantity": 0.0,
                    "avg_fill_price": None,
                    "leverage": 10,
                    "margin_mode": "cross",
                    "pos_side": "long",
                    "reduce_only": False,
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
    """A single fill (execution) against an order.

    Mirrors OKX ``/api/v5/trade/fills-history`` response fields:
    ``fillPx``, ``fillSz``, ``fillPnl``, ``execType``, ``feeRate``,
    ``side``, ``posSide``, ``fee``.
    """

    id: str = Field(..., description="Unique fill identifier")
    order_id: str = Field(..., description="Parent order ID")
    price: float = Field(..., gt=0, description="Execution price (OKX fillPx)")
    quantity: float = Field(..., gt=0, description="Executed quantity in USDT notional (OKX fillSz)")
    fee: float = Field(0.0, ge=0, description="Fee charged for this fill (OKX fee)")
    fee_currency: str = Field("USDT", description="Currency of the fee (OKX feeCcy)")
    fee_rate: float = Field(0.0, ge=0, description="Fee rate applied (OKX feeRate)")
    realized_pnl: float = Field(0.0, description="Realized PnL from this fill (OKX fillPnl)")
    exec_type: str = Field("taker", description="Liquidity type: maker or taker (OKX execType)")
    side: str = Field("", description="Order side: buy or sell (OKX side)")
    pos_side: str = Field("", description="Position side: long/short/net (OKX posSide)")
    symbol: str = Field("", description="Instrument ID (OKX instId)")
    leverage: int = Field(1, ge=1, description="Leverage multiplier")
    reduce_only: bool = Field(False, description="Whether this fill closes a position")
    timestamp: Timestamp = Field(..., description="Fill time (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "fill-001",
                    "order_id": "ord-001",
                    "price": 67000.0,
                    "quantity": 10000.0,
                    "fee": 5.0,
                    "fee_currency": "USDT",
                    "fee_rate": 0.0005,
                    "realized_pnl": 0.0,
                    "exec_type": "taker",
                    "side": "buy",
                    "pos_side": "long",
                    "symbol": "BTC-USDT-SWAP",
                    "leverage": 10,
                    "reduce_only": False,
                    "timestamp": 1711000001000,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


class Position(BaseModel):
    """An open or closed trading position with derivatives support.

    Mirrors OKX position data: includes leverage, margin, liquidation price,
    and position-side awareness for dual-position mode.
    """

    symbol: Symbol = Field(..., description="Normalized trading pair")
    side: OrderSide = Field(..., description="Position direction (buy=long, sell=short)")
    pos_side: PositionSide = Field(PositionSide.NET, description="Position side for dual-mode")
    quantity: float = Field(..., ge=0, description="Position size in USDT notional")
    quantity_base: float = Field(0.0, ge=0, description="Position size in base currency")
    avg_entry_price: float = Field(..., gt=0, description="Average entry price")
    leverage: int = Field(1, ge=1, le=125, description="Leverage multiplier")
    margin_mode: MarginMode = Field(MarginMode.CROSS, description="Margin mode")
    margin: float = Field(0.0, ge=0, description="Required margin (USDT)")
    liquidation_price: float | None = Field(None, description="Estimated liquidation price")
    unrealized_pnl: float = Field(0.0, description="Unrealized profit/loss")
    unrealized_pnl_pct: float = Field(0.0, description="Unrealized PnL as percentage of margin")
    realized_pnl: float = Field(0.0, description="Realized profit/loss")
    current_price: float | None = Field(None, description="Latest mark price")
    opened_at: Timestamp = Field(..., description="Position open time (ms epoch)")
    updated_at: Timestamp = Field(..., description="Last update time (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "symbol": "BTC-USDT-SWAP",
                    "side": "buy",
                    "pos_side": "long",
                    "quantity": 1000.0,
                    "quantity_base": 0.015,
                    "avg_entry_price": 67000.0,
                    "leverage": 10,
                    "margin_mode": "cross",
                    "margin": 100.0,
                    "liquidation_price": 60300.0,
                    "unrealized_pnl": 15.0,
                    "unrealized_pnl_pct": 15.0,
                    "realized_pnl": 0.0,
                    "current_price": 68000.0,
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


# ---------------------------------------------------------------------------
# Exchange-originated private events (WS push)
# ---------------------------------------------------------------------------


class ExchangeOrderUpdate(BaseModel):
    """Real-time order status change pushed from an exchange private WS channel.

    Distinct from ``Order`` which is our internal model — this captures the
    raw exchange event with exchange-native identifiers and status strings.
    """

    exchange: str = Field(..., description="Exchange identifier, e.g. 'binance'")
    exchange_order_id: str = Field(..., description="Exchange-assigned order ID")
    client_order_id: str | None = Field(None, description="Client-assigned order ID")
    symbol: Symbol = Field(..., description="Normalized trading pair")
    side: OrderSide
    order_type: str = Field(..., description="Exchange-native order type string")
    status: str = Field(..., description="Exchange-native status (NEW/PARTIALLY_FILLED/FILLED/CANCELED)")
    quantity: float = Field(..., ge=0)
    filled_quantity: float = Field(0.0, ge=0)
    avg_fill_price: float = Field(0.0, ge=0)
    last_fill_price: float = Field(0.0, ge=0)
    last_fill_quantity: float = Field(0.0, ge=0)
    commission: float = Field(0.0, ge=0)
    commission_asset: str | None = None
    timestamp: Timestamp
    raw: dict[str, Any] | None = Field(None, description="Raw exchange payload for debugging")


class BalanceUpdate(BaseModel):
    """Account balance snapshot for a single asset, pushed via private WS."""

    exchange: str = Field(..., description="Exchange identifier")
    asset: str = Field(..., description="Asset ticker, e.g. 'BTC'")
    free: float = Field(0.0, ge=0, description="Available balance")
    locked: float = Field(0.0, ge=0, description="Balance locked in open orders")
    timestamp: Timestamp


class AccountSnapshot(BaseModel):
    """Full account balance snapshot, typically from REST reconciliation."""

    exchange: str = Field(..., description="Exchange identifier")
    balances: list[BalanceUpdate] = Field(default_factory=list)
    timestamp: Timestamp
