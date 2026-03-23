"""Unified trading endpoints — mode-agnostic order, position, and balance API.

All endpoints delegate to the current ExecutionEngine (Paper or Live).
The mode is selected at startup or switched via PUT /trading/mode.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import (
    get_execution_engine,
    get_execution_mode,
    set_execution_engine,
    set_execution_mode,
)
from pnlclaw_types.trading import (
    BalanceUpdate,
    ExecutionMode,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)

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
    symbol: str = Field(..., description="Trading pair, e.g. 'BTC/USDT'")
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(..., gt=0)
    price: float | None = Field(None, ge=0)
    stop_price: float | None = Field(None, ge=0)
    account_id: str = Field(DEFAULT_ACCOUNT, description="Account ID")


class CancelOrderRequest(BaseModel):
    order_id: str


# ---------------------------------------------------------------------------
# Mode endpoints
# ---------------------------------------------------------------------------


@router.get("/mode", response_model=TradingModeResponse)
async def get_mode(mode: str = Depends(get_execution_mode)) -> TradingModeResponse:
    """Get the current trading execution mode."""
    return TradingModeResponse(mode=mode)


@router.put("/mode", response_model=TradingModeResponse)
async def set_mode(req: TradingModeRequest) -> TradingModeResponse:
    """Switch trading execution mode.

    Note: switching to 'live' requires exchange API keys to be configured.
    Currently only 'paper' mode is available without configuration.
    """
    set_execution_mode(req.mode.value)
    return TradingModeResponse(mode=req.mode.value)


# ---------------------------------------------------------------------------
# Order endpoints
# ---------------------------------------------------------------------------


@router.post("/orders", response_model=Order)
async def place_order(
    req: PlaceOrderRequest,
    engine: object = Depends(get_execution_engine),
) -> Order:
    """Place a new order in the current execution mode."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Execution engine not available")

    return await engine.place_order(  # type: ignore[union-attr]
        account_id=req.account_id,
        symbol=req.symbol,
        side=req.side,
        order_type=req.order_type,
        quantity=req.quantity,
        price=req.price,
        stop_price=req.stop_price,
    )


@router.delete("/orders/{order_id}", response_model=Order)
async def cancel_order(
    order_id: str,
    engine: object = Depends(get_execution_engine),
) -> Order:
    """Cancel an open order."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Execution engine not available")

    try:
        return await engine.cancel_order(order_id)  # type: ignore[union-attr]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/orders", response_model=list[Order])
async def get_orders(
    account_id: str = DEFAULT_ACCOUNT,
    status: OrderStatus | None = None,
    engine: object = Depends(get_execution_engine),
) -> list[Order]:
    """Get orders, optionally filtered by status."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Execution engine not available")

    return await engine.get_orders(account_id, status=status)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Position endpoints
# ---------------------------------------------------------------------------


@router.get("/positions", response_model=list[Position])
async def get_positions(
    account_id: str = DEFAULT_ACCOUNT,
    engine: object = Depends(get_execution_engine),
) -> list[Position]:
    """Get all open positions."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Execution engine not available")

    return await engine.get_positions(account_id)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Balance endpoints
# ---------------------------------------------------------------------------


@router.get("/balances", response_model=list[BalanceUpdate])
async def get_balances(
    account_id: str = DEFAULT_ACCOUNT,
    engine: object = Depends(get_execution_engine),
) -> list[BalanceUpdate]:
    """Get account balances."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Execution engine not available")

    return await engine.get_balances(account_id)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# History endpoints
# ---------------------------------------------------------------------------


@router.get("/history", response_model=list[Fill])
async def get_trade_history(
    account_id: str = DEFAULT_ACCOUNT,
    engine: object = Depends(get_execution_engine),
) -> list[Fill]:
    """Get trade execution history (fills)."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Execution engine not available")

    return await engine.get_fills(account_id)  # type: ignore[union-attr]
