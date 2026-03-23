"""Polymarket-specific data models.

Polymarket is a prediction market, not a traditional crypto exchange.
Its data model is fundamentally different: markets are questions with
binary outcomes, and tokens represent YES/NO positions.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PolymarketToken(BaseModel):
    """A single outcome token in a Polymarket market."""

    token_id: str
    outcome: str = ""
    price: float = 0.0
    winner: bool = False


class PolymarketMarket(BaseModel):
    """A Polymarket prediction market (question)."""

    condition_id: str
    question_id: str = ""
    question: str
    description: str = ""
    market_slug: str = ""
    end_date_iso: str | None = None
    active: bool = True
    closed: bool = False
    resolved: bool = False
    resolution_source: str = ""
    winning_outcome: str = ""
    tokens: list[PolymarketToken] = Field(default_factory=list)
    volume: float = 0.0
    volume_24h: float = 0.0
    liquidity: float = 0.0


class PolymarketOrderBook(BaseModel):
    """Polymarket order book for a single token."""

    market: str = ""
    asset_id: str
    timestamp: str = ""
    bids: list[dict[str, str]] = Field(default_factory=list)
    asks: list[dict[str, str]] = Field(default_factory=list)
    last_trade_price: str = ""
    tick_size: str = "0.01"
    min_order_size: str = "1"


class PolymarketPrice(BaseModel):
    """Midpoint / market price for a token."""

    token_id: str
    price: float
    side: str = ""


# ---------------------------------------------------------------------------
# Position & redemption models
# ---------------------------------------------------------------------------


class PolymarketPositionStatus(str, Enum):
    """Position lifecycle status."""

    OPEN = "open"
    CLOSED = "closed"
    REDEEMABLE = "redeemable"
    REDEEMED = "redeemed"


class PolymarketPosition(BaseModel):
    """A user's position in a Polymarket market."""

    condition_id: str = Field(..., description="Market condition ID")
    asset_id: str = Field("", description="Token/asset ID for this position leg")
    title: str = Field("", description="Market question title")
    outcome: str = Field("", description="Position outcome (YES/NO)")
    size: float = Field(0.0, ge=0, description="Number of shares held")
    avg_price: float = Field(0.0, ge=0, description="Average entry price per share")
    current_price: float = Field(0.0, ge=0, description="Current market price")
    current_value: float = Field(0.0, ge=0, description="Current position value in USDC")
    cost_basis: float = Field(0.0, ge=0, description="Total cost basis in USDC")
    cash_pnl: float = Field(0.0, description="Realized PnL in USDC")
    percent_pnl: float = Field(0.0, description="PnL as percentage")
    redeemable: bool = Field(False, description="Whether this position can be redeemed")
    is_winner: bool = Field(False, description="Whether this is the winning outcome")
    status: PolymarketPositionStatus = Field(
        PolymarketPositionStatus.OPEN, description="Position status"
    )


class RedemptionResult(BaseModel):
    """Result of a token redemption operation."""

    condition_id: str = Field(..., description="Market condition ID")
    outcome: str = Field("", description="Outcome that was redeemed")
    shares_redeemed: float = Field(0.0, ge=0, description="Number of shares burned")
    usdc_received: float = Field(0.0, ge=0, description="USDC.e received from redemption")
    transaction_hash: str = Field("", description="On-chain transaction hash")
    success: bool = Field(False, description="Whether redemption succeeded")
    error: str = Field("", description="Error message if redemption failed")


class AutoRedeemSummary(BaseModel):
    """Summary of an auto-redemption sweep."""

    markets_checked: int = Field(0, description="Number of markets checked")
    redeemable_found: int = Field(0, description="Number of redeemable positions")
    redemptions_attempted: int = Field(0, description="Number of redemptions attempted")
    redemptions_succeeded: int = Field(0, description="Number successful")
    total_usdc_redeemed: float = Field(0.0, description="Total USDC.e recovered")
    results: list[RedemptionResult] = Field(
        default_factory=list, description="Per-position results"
    )
