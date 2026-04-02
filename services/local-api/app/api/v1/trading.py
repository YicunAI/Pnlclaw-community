"""Unified trading endpoints — mode-agnostic order, position, and balance API.

All endpoints delegate to the current ExecutionEngine (Paper or Live).
The mode is selected at startup or switched via PUT /trading/mode.
Risk engine pre-checks are applied before every order placement.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import (
    AuthenticatedUser,
    get_execution_mode,
    get_live_engine,
    get_risk_engine,
    optional_user,
    set_execution_mode,
)
from pnlclaw_types.trading import (
    BalanceUpdate,
    ExecutionMode,
    Fill,
    MarginMode,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trading", tags=["trading"])

DEFAULT_ACCOUNT = "paper-default"


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class TradingModeResponse(BaseModel):
    mode: str = Field(..., description="Current execution mode: 'paper' or 'live'")


class TradingModeRequest(BaseModel):
    mode: ExecutionMode = Field(..., description="Target mode: 'paper' or 'live'")


class PlaceOrderRequest(BaseModel):
    symbol: str = Field(..., description="Instrument, e.g. 'BTC-USDT-SWAP'")
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(..., gt=0, description="Order size in USDT")
    price: float | None = Field(None, ge=0)
    stop_price: float | None = Field(None, ge=0)
    leverage: int = Field(1, ge=1, le=125, description="Leverage")
    margin_mode: MarginMode = Field(MarginMode.CROSS)
    pos_side: PositionSide = Field(PositionSide.LONG)
    reduce_only: bool = Field(False)
    account_id: str = Field(DEFAULT_ACCOUNT, description="Account ID")


class CancelOrderRequest(BaseModel):
    order_id: str


# ---------------------------------------------------------------------------
# Mode endpoints
# ---------------------------------------------------------------------------


@router.get("/mode", response_model=TradingModeResponse)
async def get_mode(
    mode: str = Depends(get_execution_mode),
    user: AuthenticatedUser = Depends(optional_user),
) -> TradingModeResponse:
    """Get the current trading execution mode."""
    return TradingModeResponse(mode=mode)


@router.put("/mode", response_model=TradingModeResponse)
async def set_mode(
    req: TradingModeRequest,
    user: AuthenticatedUser = Depends(optional_user),
) -> TradingModeResponse:
    """Switch trading execution mode."""
    if req.mode == ExecutionMode.LIVE:
        raise HTTPException(
            status_code=400,
            detail="Live trading is not available in Community v0.1. Use paper mode.",
        )
    set_execution_mode(req.mode.value)
    return TradingModeResponse(mode=req.mode.value)


# ---------------------------------------------------------------------------
# Order endpoints
# ---------------------------------------------------------------------------


@router.post("/orders", response_model=Order)
async def place_order(
    req: PlaceOrderRequest,
    engine: object = Depends(get_live_engine),
    user: AuthenticatedUser = Depends(optional_user),
) -> Order:
    """Place a new order in the live mode.

    Applies risk engine pre-check before delegating to the execution engine.
    """
    if engine is None:
        raise HTTPException(status_code=503, detail="Live execution engine not configured. Please add API keys.")

    # Risk pre-check
    risk_engine = get_risk_engine()
    if risk_engine is not None:
        try:
            import time

            from pnlclaw_types.agent import TradeIntent

            intent = TradeIntent(
                symbol=req.symbol,
                side=req.side,
                quantity=req.quantity,
                price=req.price,
                reasoning="User manual order",
                confidence=1.0,
                risk_params={"stop_loss": req.stop_price} if req.stop_price else {},
                timestamp=int(time.time() * 1000),
            )

            # Build context from current account state
            ctx: dict = {}
            try:
                balances = await engine.get_balances(req.account_id)  # type: ignore[union-attr]
                if balances:
                    ctx["total_equity"] = sum(b.free + b.locked for b in balances)
                positions = await engine.get_positions(req.account_id)  # type: ignore[union-attr]
                if positions:
                    ctx["positions"] = {p.symbol: p.quantity * p.avg_entry_price for p in positions}
            except Exception:
                logger.debug(
                    "Risk pre-check: failed to load balances or positions for context",
                    exc_info=True,
                )

            decision = risk_engine.pre_check(intent, ctx)
            if not decision.allowed:
                raise HTTPException(
                    status_code=403,
                    detail=f"Risk check failed: {decision.reason}",
                )
        except HTTPException:
            raise
        except ImportError:
            logger.debug("pnlclaw_types.agent not available for risk check")
        except Exception:
            logger.warning("Risk pre-check error (allowing trade)", exc_info=True)

    return await engine.place_order(  # type: ignore[union-attr]
        account_id=req.account_id,
        symbol=req.symbol,
        side=req.side,
        order_type=req.order_type,
        quantity=req.quantity,
        price=req.price,
        stop_price=req.stop_price,
        leverage=req.leverage,
        margin_mode=req.margin_mode,
        pos_side=req.pos_side,
        reduce_only=req.reduce_only,
    )


@router.delete("/orders/{order_id}", response_model=Order)
async def cancel_order(
    order_id: str,
    engine: object = Depends(get_live_engine),
    user: AuthenticatedUser = Depends(optional_user),
) -> Order:
    """Cancel an open order."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Live execution engine not configured. Please add API keys.")

    try:
        return await engine.cancel_order(order_id)  # type: ignore[union-attr]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/orders", response_model=list[Order])
async def get_orders(
    account_id: str = DEFAULT_ACCOUNT,
    status: OrderStatus | None = None,
    engine: object = Depends(get_live_engine),
    user: AuthenticatedUser = Depends(optional_user),
) -> list[Order]:
    """Get orders, optionally filtered by status."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Live execution engine not configured. Please add API keys.")

    return await engine.get_orders(account_id, status=status)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Position endpoints
# ---------------------------------------------------------------------------


@router.get("/positions", response_model=list[Position])
async def get_positions(
    account_id: str = DEFAULT_ACCOUNT,
    engine: object = Depends(get_live_engine),
    user: AuthenticatedUser = Depends(optional_user),
) -> list[Position]:
    """Get all open positions."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Live execution engine not configured. Please add API keys.")

    return await engine.get_positions(account_id)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Balance endpoints
# ---------------------------------------------------------------------------


@router.get("/balances", response_model=list[BalanceUpdate])
async def get_balances(
    account_id: str = DEFAULT_ACCOUNT,
    engine: object = Depends(get_live_engine),
    user: AuthenticatedUser = Depends(optional_user),
) -> list[BalanceUpdate]:
    """Get account balances."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Live execution engine not configured. Please add API keys.")

    return await engine.get_balances(account_id)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# History endpoints
# ---------------------------------------------------------------------------


@router.get("/history", response_model=list[Fill])
async def get_trade_history(
    account_id: str = DEFAULT_ACCOUNT,
    engine: object = Depends(get_live_engine),
    user: AuthenticatedUser = Depends(optional_user),
) -> list[Fill]:
    """Get trade execution history (fills)."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Live execution engine not configured. Please add API keys.")

    return await engine.get_fills(account_id)  # type: ignore[union-attr]
