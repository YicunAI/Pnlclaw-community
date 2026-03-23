"""Paper Trading endpoints.

Provides account management, order placement, position queries,
and PnL calculation through the ``pnlclaw_paper`` package managers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from pnlclaw_types.common import APIResponse, Pagination
from pnlclaw_types.errors import ErrorCode, NotFoundError, PnLClawError
from pnlclaw_types.trading import OrderSide, OrderStatus, OrderType

from app.core.dependencies import (
    build_response_meta,
    get_paper_account_manager,
    get_paper_order_manager,
    get_paper_position_manager,
)

router = APIRouter(prefix="/paper", tags=["paper-trading"])


# ---------------------------------------------------------------------------
# Fallback in-memory managers (used when packages not injected via DI)
# ---------------------------------------------------------------------------

_fallback_initialized = False
_fallback_accounts: Any = None
_fallback_orders: Any = None
_fallback_positions: Any = None


def _ensure_fallback() -> tuple[Any, Any, Any]:
    """Lazily create fallback managers from pnlclaw_paper."""
    global _fallback_initialized, _fallback_accounts, _fallback_orders, _fallback_positions
    if not _fallback_initialized:
        try:
            from pnlclaw_paper.accounts import AccountManager
            from pnlclaw_paper.orders import PaperOrderManager
            from pnlclaw_paper.positions import PositionManager

            _fallback_accounts = AccountManager()
            _fallback_orders = PaperOrderManager()
            _fallback_positions = PositionManager()
        except ImportError:
            pass
        _fallback_initialized = True
    return _fallback_accounts, _fallback_orders, _fallback_positions


def _get_accounts(mgr: Any = Depends(get_paper_account_manager)) -> Any:
    if mgr is not None:
        return mgr
    accts, _, _ = _ensure_fallback()
    if accts is None:
        raise PnLClawError(ErrorCode.SERVICE_UNAVAILABLE, "Paper account manager unavailable")
    return accts


def _get_orders(mgr: Any = Depends(get_paper_order_manager)) -> Any:
    if mgr is not None:
        return mgr
    _, orders, _ = _ensure_fallback()
    if orders is None:
        raise PnLClawError(ErrorCode.SERVICE_UNAVAILABLE, "Paper order manager unavailable")
    return orders


def _get_positions(mgr: Any = Depends(get_paper_position_manager)) -> Any:
    if mgr is not None:
        return mgr
    _, _, pos = _ensure_fallback()
    if pos is None:
        raise PnLClawError(ErrorCode.SERVICE_UNAVAILABLE, "Paper position manager unavailable")
    return pos


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateAccountRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Account name")
    initial_balance: float = Field(10_000.0, gt=0, description="Starting balance")


class PlaceOrderRequest(BaseModel):
    account_id: str = Field(..., description="Paper account ID")
    symbol: str = Field(..., description="Trading pair")
    side: OrderSide = Field(..., description="buy or sell")
    order_type: OrderType = Field(OrderType.MARKET, description="Order type")
    quantity: float = Field(..., gt=0, description="Order quantity")
    price: float | None = Field(None, gt=0, description="Limit price (required for limit orders)")
    stop_price: float | None = Field(None, gt=0, description="Stop price")


# ---------------------------------------------------------------------------
# Account endpoints
# ---------------------------------------------------------------------------


@router.post("/accounts")
async def create_account(
    request: Request,
    body: CreateAccountRequest,
    mgr: Any = Depends(_get_accounts),
) -> APIResponse[dict[str, Any]]:
    """Create a new paper trading account."""
    account = mgr.create_account(body.name, body.initial_balance)
    return APIResponse(
        data=account.model_dump(),
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/accounts")
async def list_accounts(
    request: Request,
    mgr: Any = Depends(_get_accounts),
) -> APIResponse[list[dict[str, Any]]]:
    """List all paper trading accounts."""
    accounts = mgr.list_accounts()
    return APIResponse(
        data=[a.model_dump() for a in accounts],
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: str,
    request: Request,
    mgr: Any = Depends(_get_accounts),
) -> APIResponse[dict[str, Any]]:
    """Get account details."""
    account = mgr.get_account(account_id)
    if account is None:
        raise NotFoundError(f"Account '{account_id}' not found")
    return APIResponse(
        data=account.model_dump(),
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Order endpoints
# ---------------------------------------------------------------------------


@router.post("/orders")
async def place_order(
    request: Request,
    body: PlaceOrderRequest,
    accounts: Any = Depends(_get_accounts),
    orders: Any = Depends(_get_orders),
) -> APIResponse[dict[str, Any]]:
    """Place a paper trading order."""
    # Verify account exists
    account = accounts.get_account(body.account_id)
    if account is None:
        raise NotFoundError(f"Account '{body.account_id}' not found")

    order = orders.place_order(
        account_id=body.account_id,
        symbol=body.symbol,
        side=body.side,
        order_type=body.order_type,
        quantity=body.quantity,
        price=body.price,
        stop_price=body.stop_price,
    )
    return APIResponse(
        data=order.model_dump(),
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/orders")
async def list_orders(
    request: Request,
    account_id: str = Query(..., description="Paper account ID"),
    status: OrderStatus | None = Query(None, description="Filter by status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    orders_mgr: Any = Depends(_get_orders),
) -> APIResponse[list[dict[str, Any]]]:
    """List orders for an account."""
    all_orders = orders_mgr.get_orders(account_id, status=status)
    total = len(all_orders)
    page = all_orders[offset : offset + limit]
    return APIResponse(
        data=[o.model_dump() for o in page],
        meta=build_response_meta(
            request,
            pagination=Pagination(offset=offset, limit=limit, total=total),
        ),
        error=None,
    )


# ---------------------------------------------------------------------------
# Position endpoints
# ---------------------------------------------------------------------------


@router.get("/positions")
async def list_positions(
    request: Request,
    account_id: str = Query(..., description="Paper account ID"),
    pos_mgr: Any = Depends(_get_positions),
) -> APIResponse[list[dict[str, Any]]]:
    """List positions for an account."""
    positions = pos_mgr.get_positions(account_id)
    return APIResponse(
        data=[p.model_dump() for p in positions],
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# PnL endpoint
# ---------------------------------------------------------------------------


@router.get("/pnl")
async def get_pnl(
    request: Request,
    account_id: str = Query(..., description="Paper account ID"),
    pos_mgr: Any = Depends(_get_positions),
) -> APIResponse[list[dict[str, Any]]]:
    """Calculate PnL for all positions of an account."""
    positions = pos_mgr.get_positions(account_id)
    try:
        from pnlclaw_paper.pnl import calculate_account_pnl

        # Use zero prices as default — in production, market prices are injected
        prices = {p.symbol: 0.0 for p in positions}
        records = calculate_account_pnl(positions, prices)
        return APIResponse(
            data=[r.model_dump() for r in records],
            meta=build_response_meta(request),
            error=None,
        )
    except ImportError:
        # Fallback: return raw position PnL fields
        return APIResponse(
            data=[
                {
                    "symbol": p.symbol,
                    "realized_pnl": p.realized_pnl,
                    "unrealized_pnl": p.unrealized_pnl,
                }
                for p in positions
            ],
            meta=build_response_meta(request),
            error=None,
        )
