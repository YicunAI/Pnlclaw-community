"""Paper Trading endpoints.

Provides account management, order placement, position queries,
and PnL calculation through the ``pnlclaw_paper`` package managers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.core.dependencies import (
    AuthenticatedUser,
    build_response_meta,
    get_db_manager,
    get_execution_engine,
    get_market_service,
    get_paper_account_manager,
    get_paper_order_manager,
    get_paper_position_manager,
    optional_user,
)
from pnlclaw_types.common import APIResponse, Pagination
from pnlclaw_types.errors import ErrorCode, NotFoundError, PnLClawError
from pnlclaw_types.trading import MarginMode, OrderSide, OrderStatus, OrderType, PositionSide

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/paper", tags=["paper-trading"])

_equity_record_timestamps: dict[str, float] = {}
EQUITY_RECORD_INTERVAL = 30.0

# ---------------------------------------------------------------------------
# Account ownership registry  (account_id → user_id)
#
# The in-memory PaperExecutionEngine / AccountManager has no concept of
# "user".  We track ownership at the API layer so each user can only see
# and operate on their own accounts.
# ---------------------------------------------------------------------------

_account_owners: dict[str, str] = {}
_owners_loaded = False


def _register_owner(account_id: str, user_id: str) -> None:
    """Record that *account_id* belongs to *user_id*."""
    _account_owners[account_id] = user_id


def _owner_of(account_id: str) -> str | None:
    """Return the user_id that owns *account_id*, or None."""
    return _account_owners.get(account_id)


async def _ensure_owners_loaded() -> None:
    """One-time load of ownership from the DB (paper_accounts.user_id)."""
    global _owners_loaded
    if _owners_loaded:
        return
    _owners_loaded = True
    try:
        db = get_db_manager()
        if db is None:
            return
        rows = await db.query("SELECT id, user_id FROM paper_accounts WHERE user_id IS NOT NULL", ())
        for r in rows:
            _account_owners[r["id"]] = r["user_id"]
        logger.info("Loaded %d paper account owner mappings from DB", len(rows))
    except Exception:
        logger.debug("Could not preload paper account owners", exc_info=True)


def _verify_ownership(account_id: str, user: AuthenticatedUser) -> None:
    """Raise 403 if the current user does not own *account_id*.

    In Community mode (user.id == "local") ownership checks are skipped.
    """
    if user.id == "local":
        return
    owner = _owner_of(account_id)
    if owner is not None and owner != user.id:
        raise PnLClawError(
            ErrorCode.PERMISSION_DENIED,
            "You do not have access to this account",
        )


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
    account_type: str = Field("manual", description="Account type: strategy, agent, or manual")
    strategy_id: str | None = Field(None, description="Linked strategy ID (for strategy accounts)")


class PlaceOrderRequest(BaseModel):
    account_id: str = Field(..., description="Paper account ID")
    symbol: str = Field(..., description="Instrument, e.g. BTC-USDT-SWAP")
    side: OrderSide = Field(..., description="buy or sell")
    order_type: OrderType = Field(OrderType.MARKET, description="Order type")
    quantity: float = Field(..., gt=0, description="Order size in USDT")
    price: float | None = Field(None, gt=0, description="Limit price")
    stop_price: float | None = Field(None, gt=0, description="Stop price")
    leverage: int = Field(1, ge=1, le=125, description="Leverage multiplier")
    margin_mode: MarginMode = Field(MarginMode.CROSS, description="cross or isolated")
    pos_side: PositionSide = Field(PositionSide.LONG, description="long or short")
    reduce_only: bool = Field(False, description="Close position only")
    mark_price: float | None = Field(None, gt=0, description="Frontend mark price for fill simulation")
    tp_price: float | None = Field(None, gt=0, description="Take-profit trigger price")
    sl_price: float | None = Field(None, gt=0, description="Stop-loss trigger price")


class ClosePositionRequest(BaseModel):
    account_id: str = Field(..., description="Paper account ID")
    symbol: str = Field(..., description="Instrument")
    pos_side: PositionSide = Field(..., description="Position side to close")
    quantity: float | None = Field(None, gt=0, description="Close amount in USDT (None=close all)")
    mark_price: float | None = Field(None, gt=0, description="Mark price for market close")


# ---------------------------------------------------------------------------
# Account endpoints
# ---------------------------------------------------------------------------


def _refresh_unrealized_pnl(account_id: str, pos_mgr: Any) -> None:
    """Update unrealized PnL on all open positions with latest market prices."""
    engine = get_execution_engine()
    market_svc = get_market_service()
    if pos_mgr is None:
        return
    positions = pos_mgr.get_open_positions(account_id)
    for p in positions:
        price = _get_live_price(p.symbol, engine, market_svc)
        if price is not None and price > 0:
            pos_mgr.update_unrealized_pnl(account_id, p.symbol, price)


@router.get("/accounts")
async def list_accounts(
    request: Request,
    mgr: Any = Depends(_get_accounts),
    pos_mgr: Any = Depends(_get_positions),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[list[dict[str, Any]]]:
    """List paper trading accounts owned by the current user.

    Equity = wallet_balance + unrealized PnL.
    wallet_balance = initial_balance + total_realized_pnl - total_fee.
    """
    import time as _time

    await _ensure_owners_loaded()

    all_accounts = mgr.list_accounts()

    if user.id == "local":
        accounts = all_accounts
    else:
        accounts = [a for a in all_accounts if _owner_of(a.id) == user.id]

        if not accounts:
            new_acct = mgr.create_account(
                name="Default Paper Account",
                initial_balance=100_000.0,
            )
            _register_owner(new_acct.id, user.id)
            db = get_db_manager()
            if db is not None:
                try:
                    from pnlclaw_storage.repositories.paper_accounts import PaperAccountRepository

                    repo = PaperAccountRepository(db)
                    await repo.save_account(new_acct.model_dump(), user_id=user.id)
                except Exception:
                    logger.debug("Failed to persist auto-created paper account", exc_info=True)
            accounts = [new_acct]

    result = []
    now = _time.time()
    for a in accounts:
        _refresh_unrealized_pnl(a.id, pos_mgr)
        data = a.model_dump()
        unrealized = sum(p.unrealized_pnl for p in pos_mgr.get_open_positions(a.id))
        wallet_balance = a.initial_balance + a.total_realized_pnl - a.total_fee
        equity = wallet_balance + unrealized
        data["equity"] = equity
        data["balance"] = a.current_balance
        data["unrealized_pnl"] = unrealized
        data["realized_pnl"] = a.total_realized_pnl
        result.append(data)

        last_ts = _equity_record_timestamps.get(a.id, 0.0)
        if now - last_ts >= EQUITY_RECORD_INTERVAL:
            _equity_record_timestamps[a.id] = now
            asyncio.create_task(_record_equity(a.id, equity))

    return APIResponse(
        data=result,
        meta=build_response_meta(request),
        error=None,
    )


@router.post("/accounts")
async def create_account(
    request: Request,
    body: CreateAccountRequest,
    mgr: Any = Depends(_get_accounts),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Create a new paper trading account owned by the current user."""
    kwargs: dict[str, Any] = {
        "name": body.name,
        "initial_balance": body.initial_balance,
    }
    try:
        from pnlclaw_paper.accounts import AccountType

        type_map = {t.value: t for t in AccountType}
        if body.account_type in type_map:
            kwargs["account_type"] = type_map[body.account_type]
        if body.strategy_id:
            kwargs["strategy_id"] = body.strategy_id
    except ImportError:
        pass

    account = mgr.create_account(**kwargs)

    _register_owner(account.id, user.id)

    data = account.model_dump()
    data["equity"] = account.initial_balance
    data["balance"] = account.current_balance
    data["unrealized_pnl"] = 0.0
    data["realized_pnl"] = 0.0

    db = get_db_manager()
    if db is not None:
        try:
            from pnlclaw_storage.repositories.paper_accounts import PaperAccountRepository

            repo = PaperAccountRepository(db)
            await repo.save_account(account.model_dump(), user_id=user.id)
        except Exception:
            logger.debug("Failed to persist paper account with user_id", exc_info=True)

    return APIResponse(data=data, meta=build_response_meta(request), error=None)


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: str,
    request: Request,
    mgr: Any = Depends(_get_accounts),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Delete a paper trading account (must be owned by current user)."""
    _verify_ownership(account_id, user)
    deleted = mgr.delete_account(account_id)
    if not deleted:
        raise NotFoundError(f"Paper account '{account_id}' not found")
    _account_owners.pop(account_id, None)
    return APIResponse(data={"deleted": account_id}, meta=build_response_meta(request), error=None)


@router.post("/accounts/{account_id}/reset")
async def reset_account(
    account_id: str,
    request: Request,
    mgr: Any = Depends(_get_accounts),
    engine: Any = Depends(get_execution_engine),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Reset a paper trading account to initial state."""
    _verify_ownership(account_id, user)
    if engine is not None and hasattr(engine, "reset_account"):
        success = engine.reset_account(account_id)
        if not success:
            raise NotFoundError(f"Paper account '{account_id}' not found")
        account = mgr.get_account(account_id)
    else:
        account = mgr.reset_account(account_id)
    if account is None:
        raise NotFoundError(f"Paper account '{account_id}' not found")

    try:
        db = request.app.state.db if hasattr(request.app.state, "db") else None
        if db:
            from pnlclaw_storage.repositories.paper_accounts import PaperAccountRepository

            repo = PaperAccountRepository(db)
            await repo.clear_equity_history(account_id)
            await repo.save_equity_point(account_id, account.initial_balance)
    except Exception:
        logger.warning("Failed to clear equity history on reset for %s", account_id, exc_info=True)

    data = account.model_dump()
    data["equity"] = account.initial_balance
    data["balance"] = account.current_balance
    data["unrealized_pnl"] = 0.0
    data["realized_pnl"] = 0.0
    return APIResponse(data=data, meta=build_response_meta(request), error=None)


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: str,
    request: Request,
    mgr: Any = Depends(_get_accounts),
    pos_mgr: Any = Depends(_get_positions),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Get account details with live equity."""
    _verify_ownership(account_id, user)
    account = mgr.get_account(account_id)
    if account is None:
        raise NotFoundError(f"Account '{account_id}' not found")
    _refresh_unrealized_pnl(account_id, pos_mgr)
    data = account.model_dump()
    unrealized = sum(p.unrealized_pnl for p in pos_mgr.get_open_positions(account_id))
    wallet_balance = account.initial_balance + account.total_realized_pnl - account.total_fee
    data["equity"] = wallet_balance + unrealized
    asyncio.create_task(_record_equity(account_id, data["equity"]))

    data["balance"] = account.current_balance
    data["unrealized_pnl"] = unrealized
    data["realized_pnl"] = account.total_realized_pnl
    return APIResponse(
        data=data,
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Order endpoints
# ---------------------------------------------------------------------------


def _swap_symbol_to_ticker(symbol: str) -> str:
    """Convert SWAP symbol to ticker format for market data lookup.

    ``BTC-USDT-SWAP`` → ``BTC/USDT``
    ``ETH-USDT-SWAP`` → ``ETH/USDT``
    Already-normalized symbols like ``BTC/USDT`` pass through unchanged.
    """
    s = symbol.upper().replace("-SWAP", "")
    if "/" in s:
        return s
    if "-" in s:
        parts = s.split("-", 1)
        return f"{parts[0]}/{parts[1]}"
    return s


@router.post("/orders")
async def place_order(
    request: Request,
    body: PlaceOrderRequest,
    accounts: Any = Depends(_get_accounts),
    orders: Any = Depends(_get_orders),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Place a paper trading order.

    Always delegates to PaperExecutionEngine which guarantees immediate fill
    for market orders.  The engine accepts ``mark_price`` from the frontend
    as a fallback fill price when its internal price cache is empty.
    """
    _verify_ownership(body.account_id, user)
    account = accounts.get_account(body.account_id)
    if account is None:
        raise NotFoundError(f"Account '{body.account_id}' not found")

    engine = get_execution_engine()

    if engine is not None:
        try:
            order = await engine.place_order(
                account_id=body.account_id,
                symbol=body.symbol,
                side=body.side,
                order_type=body.order_type,
                quantity=body.quantity,
                price=body.price,
                stop_price=body.stop_price,
                leverage=body.leverage,
                margin_mode=body.margin_mode,
                pos_side=body.pos_side,
                reduce_only=body.reduce_only,
                mark_price=body.mark_price,
            )
            return APIResponse(
                data=order.model_dump(),
                meta=build_response_meta(request),
                error=None,
            )
        except ValueError as exc:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Engine not available — direct order manager fallback
    logger.warning("Execution engine not available, using raw order manager")

    order = orders.place_order(
        account_id=body.account_id,
        symbol=body.symbol,
        side=body.side,
        order_type=body.order_type,
        quantity=body.quantity,
        price=body.price,
        stop_price=body.stop_price,
        leverage=body.leverage,
        margin_mode=body.margin_mode,
        pos_side=body.pos_side,
        reduce_only=body.reduce_only,
    )

    if body.order_type == OrderType.MARKET:
        fill_price = body.mark_price or body.price
        if fill_price is None:
            market_svc = get_market_service()
            if market_svc is not None:
                try:
                    ticker = market_svc.get_ticker(_swap_symbol_to_ticker(body.symbol))
                    if ticker is not None:
                        fill_price = ticker.last_price
                except Exception:
                    pass

        if fill_price and fill_price > 0:
            try:
                from pnlclaw_paper.fills import try_fill

                fill = try_fill(order, fill_price, fee_rate=0.001)
                if fill is not None:
                    orders.update_fill(order.id, fill.quantity, fill.price)
            except Exception:
                logger.debug("Fallback fill failed", exc_info=True)

    # Record equity point after order placement
    try:
        unrealized = 0.0
        from app.core.dependencies import get_paper_position_manager

        pos_mgr = get_paper_position_manager()
        if pos_mgr:
            unrealized = sum(p.unrealized_pnl for p in pos_mgr.get_open_positions(body.account_id))
        wallet_bal = account.initial_balance + account.total_realized_pnl - account.total_fee
        asyncio.create_task(_record_equity(body.account_id, wallet_bal + unrealized))
    except Exception:
        logger.debug(
            "Post-order equity snapshot: failed to record equity",
            exc_info=True,
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
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[list[dict[str, Any]]]:
    """List orders for an account (must be owned by current user)."""
    _verify_ownership(account_id, user)
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


@router.delete("/orders/{order_id}")
async def cancel_order_endpoint(
    order_id: str,
    request: Request,
    orders_mgr: Any = Depends(_get_orders),
    accounts: Any = Depends(_get_accounts),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Cancel a pending paper trading order and release frozen margin."""
    engine = get_execution_engine()

    try:
        if engine is not None and hasattr(engine, "cancel_order"):
            order = await engine.cancel_order(order_id)
        else:
            order = orders_mgr.cancel_order(order_id)

        account = None
        account_id = None

        if order is not None:
            for acct_id, oids in orders_mgr._account_orders.items():
                if order_id in oids:
                    account_id = acct_id
                    break

            if account_id:
                _verify_ownership(account_id, user)
                account = accounts.get_account(account_id)
                if account is not None:
                    remaining_qty = order.quantity - order.filled_quantity
                    if remaining_qty > 0 and order.leverage and order.leverage > 0:
                        released_margin = remaining_qty / order.leverage
                        account.current_balance += released_margin
                        logger.info(
                            "Released %.2f USDT margin for cancelled order %s",
                            released_margin,
                            order_id,
                        )

        if account is not None and account_id is not None:
            unrealized = 0.0
            from app.core.dependencies import get_paper_position_manager

            pos_mgr = get_paper_position_manager()
            if pos_mgr:
                unrealized = sum(p.unrealized_pnl for p in pos_mgr.get_open_positions(account_id))
            wallet_bal = account.initial_balance + account.total_realized_pnl - account.total_fee
            asyncio.create_task(_record_equity(account_id, wallet_bal + unrealized))

        return APIResponse(
            data=order.model_dump() if order else {"id": order_id, "status": "cancelled"},
            meta=build_response_meta(request),
            error=None,
        )
    except KeyError:
        raise NotFoundError(f"Order '{order_id}' not found")
    except Exception as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Close position endpoint
# ---------------------------------------------------------------------------


@router.post("/close-position")
async def close_position(
    request: Request,
    body: ClosePositionRequest,
    accounts: Any = Depends(_get_accounts),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Close an open position (market close).

    Places a reduce-only market order in the opposite direction.
    """
    _verify_ownership(body.account_id, user)
    account = accounts.get_account(body.account_id)
    if account is None:
        raise NotFoundError(f"Account '{body.account_id}' not found")

    engine = get_execution_engine()
    if engine is None:
        raise PnLClawError(ErrorCode.SERVICE_UNAVAILABLE, "Execution engine unavailable")

    pos_mgr = getattr(engine, "_position_mgr", None)
    if pos_mgr is None:
        raise PnLClawError(ErrorCode.SERVICE_UNAVAILABLE, "Position manager unavailable")

    positions = pos_mgr.get_positions(body.account_id)
    target = None
    for p in positions:
        if _symbols_match(p.symbol, body.symbol) and getattr(p, "pos_side", None) == body.pos_side:
            target = p
            break

    if target is None or target.quantity <= 0:
        raise NotFoundError("No open position to close")

    close_qty = body.quantity if body.quantity else target.quantity
    close_side = OrderSide.SELL if body.pos_side == PositionSide.LONG else OrderSide.BUY

    try:
        order = await engine.place_order(
            account_id=body.account_id,
            symbol=target.symbol,
            side=close_side,
            order_type=OrderType.MARKET,
            quantity=close_qty,
            price=None,
            leverage=target.leverage,
            margin_mode=target.margin_mode,
            pos_side=body.pos_side,
            reduce_only=True,
            mark_price=body.mark_price,
        )

        try:
            _refresh_unrealized_pnl(body.account_id, getattr(engine, "_position_mgr", None))
            unrealized = sum(p.unrealized_pnl for p in engine._position_mgr.get_open_positions(body.account_id))
            wallet_bal = account.initial_balance + account.total_realized_pnl - account.total_fee
            asyncio.create_task(_record_equity(body.account_id, wallet_bal + unrealized))
        except Exception:
            pass

        return APIResponse(
            data=order.model_dump(),
            meta=build_response_meta(request),
            error=None,
        )
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _symbols_match(a: str, b: str) -> bool:
    """Flexible symbol comparison across formats."""
    na = a.upper().replace("-SWAP", "").replace("-", "/")
    nb = b.upper().replace("-SWAP", "").replace("-", "/")
    return na == nb


# ---------------------------------------------------------------------------
# Position endpoints
# ---------------------------------------------------------------------------


@router.get("/positions")
async def list_positions(
    request: Request,
    account_id: str = Query(..., description="Paper account ID"),
    pos_mgr: Any = Depends(_get_positions),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[list[dict[str, Any]]]:
    """List positions for an account with live unrealized PnL."""
    _verify_ownership(account_id, user)
    positions = pos_mgr.get_positions(account_id)

    engine = get_execution_engine()
    market_svc = get_market_service()

    acct_mgr = None
    if engine is not None:
        acct_mgr = getattr(engine, "_account_mgr", None)
    acct = acct_mgr.get_account(account_id) if acct_mgr else None
    acct_balance = acct.current_balance if acct else None

    for p in positions:
        if p.quantity <= 0:
            continue
        price = _get_live_price(p.symbol, engine, market_svc)
        if price is not None and price > 0:
            pos_mgr.update_unrealized_pnl(account_id, p.symbol, price)

        if p.leverage > 1 and p.avg_entry_price > 0:
            from pnlclaw_paper.positions import _estimate_liquidation_price

            p.liquidation_price = _estimate_liquidation_price(
                p.avg_entry_price,
                p.leverage,
                p.side,
                p.margin_mode,
                available_balance=acct_balance,
                position_usdt=p.quantity,
            )

    positions = pos_mgr.get_positions(account_id)
    return APIResponse(
        data=[p.model_dump() for p in positions],
        meta=build_response_meta(request),
        error=None,
    )


def _get_live_price(symbol: str, engine: Any, market_svc: Any) -> float | None:
    """Best-effort current price from engine cache or market data service."""
    if engine is not None:
        prices = getattr(engine, "_last_prices", {})
        if symbol in prices:
            return prices[symbol]
        ticker_sym = _swap_symbol_to_ticker(symbol)
        if ticker_sym in prices:
            return prices[ticker_sym]

    if market_svc is not None:
        try:
            ticker = market_svc.get_ticker(_swap_symbol_to_ticker(symbol))
            if ticker is not None:
                return ticker.last_price
        except Exception:
            logger.debug(
                "_get_live_price: market service get_ticker failed",
                exc_info=True,
            )
    return None


# ---------------------------------------------------------------------------
# Fills / trade history endpoint
# ---------------------------------------------------------------------------


@router.get("/fills")
async def list_fills(
    request: Request,
    account_id: str = Query(..., description="Paper account ID"),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[list[dict[str, Any]]]:
    """Return actual Fill records (not orders) as trade history.

    Mirrors OKX ``/api/v5/trade/fills-history``: each record includes
    execution price, fee, fee_rate, realized PnL, exec_type, etc.
    """
    _verify_ownership(account_id, user)
    engine = get_execution_engine()
    if engine is None:
        return APIResponse(data=[], meta=build_response_meta(request), error=None)

    fills = await engine.get_fills(account_id)
    data = [f.model_dump() for f in fills]
    return APIResponse(
        data=data,
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Fee settings endpoints
# ---------------------------------------------------------------------------


class FeeSettingsRequest(BaseModel):
    maker_fee_rate: float = Field(..., ge=0, le=0.01, description="Maker fee rate (e.g. 0.0002)")
    taker_fee_rate: float = Field(..., ge=0, le=0.01, description="Taker fee rate (e.g. 0.0005)")


@router.get("/settings")
async def get_paper_settings(
    request: Request,
    account_id: str = Query("paper-default", description="Paper account ID"),
    mgr: Any = Depends(_get_accounts),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Return current paper trading settings (fee rates etc)."""
    _verify_ownership(account_id, user)
    account = mgr.get_account(account_id)
    if account is None:
        raise NotFoundError(f"Account '{account_id}' not found")
    return APIResponse(
        data={
            "account_id": account.id,
            "maker_fee_rate": account.maker_fee_rate,
            "taker_fee_rate": account.taker_fee_rate,
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.post("/settings")
async def update_paper_settings(
    request: Request,
    body: FeeSettingsRequest,
    account_id: str = Query("paper-default", description="Paper account ID"),
    mgr: Any = Depends(_get_accounts),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Update paper trading fee rates."""
    _verify_ownership(account_id, user)
    account = mgr.get_account(account_id)
    if account is None:
        raise NotFoundError(f"Account '{account_id}' not found")

    engine = get_execution_engine()
    if engine is not None and hasattr(engine, "update_fee_rates"):
        engine.update_fee_rates(account_id, body.maker_fee_rate, body.taker_fee_rate)
    else:
        account.maker_fee_rate = body.maker_fee_rate
        account.taker_fee_rate = body.taker_fee_rate

    return APIResponse(
        data={
            "account_id": account.id,
            "maker_fee_rate": account.maker_fee_rate,
            "taker_fee_rate": account.taker_fee_rate,
        },
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
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[list[dict[str, Any]]]:
    """Calculate PnL for all positions of an account."""
    _verify_ownership(account_id, user)
    positions = pos_mgr.get_positions(account_id)

    prices: dict[str, float] = {}
    market_svc = get_market_service()
    for p in positions:
        if market_svc is not None:
            try:
                ticker_sym = _swap_symbol_to_ticker(p.symbol)
                ticker = market_svc.get_ticker(ticker_sym)
                if ticker is not None:
                    prices[p.symbol] = ticker.last_price
                    continue
            except Exception:
                logger.debug(
                    "Account PnL: failed to fetch ticker for position symbol",
                    exc_info=True,
                )
        prices[p.symbol] = getattr(p, "current_price", 0.0) or 0.0

    try:
        from pnlclaw_paper.pnl import calculate_account_pnl

        records = calculate_account_pnl(positions, prices)
        return APIResponse(
            data=[r.model_dump() for r in records],
            meta=build_response_meta(request),
            error=None,
        )
    except ImportError:
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


@router.get("/accounts/{account_id}/equity-history")
async def get_equity_history_endpoint(
    account_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[list[dict[str, Any]]]:
    """Retrieve historical equity points for an account."""
    _verify_ownership(account_id, user)
    db = get_db_manager()
    if not db:
        return APIResponse(data=[], meta=build_response_meta(request))

    from pnlclaw_storage.repositories.paper_accounts import PaperAccountRepository

    repo = PaperAccountRepository(db)
    history = await repo.get_equity_history(account_id, limit)
    return APIResponse(
        data=history,
        meta=build_response_meta(request),
    )


async def _record_equity(account_id: str, equity: float):
    """Internal helper to save a snapshot of account equity.

    Ensures the account exists in the database first to satisfy foreign key constraints,
    as the PaperExecutionEngine only persists to file by default.
    """
    try:
        db = get_db_manager()
        if not db:
            logger.debug("Record equity skipped: No DB manager")
            return

        from pnlclaw_storage.repositories.paper_accounts import PaperAccountRepository

        repo = PaperAccountRepository(db)

        # 1. Sync account to DB and check for initial record
        try:
            acct_mgr = get_paper_account_manager()
            if acct_mgr:
                account = acct_mgr.get_account(account_id)
                if account:
                    owner_id = _owner_of(account_id) or "local"
                    await repo.save_account(account.model_dump(), user_id=owner_id)

                    # If this is the VERY FIRST record, insert initial_balance as the starting point
                    if not await repo.has_equity_history(account_id):
                        initial_equity = getattr(account, "initial_balance", 100000.0)
                        await repo.save_equity_point(account_id, initial_equity)
                        logger.info("Recorded initial equity for %s: %.2f", account_id, initial_equity)
        except Exception as e:
            logger.warning("Account sync/history check failed for %s: %s", account_id, e)

        # 2. Save the current equity point
        await repo.save_equity_point(account_id, equity)
        logger.info("Recorded current equity for %s: %.2f", account_id, equity)
    except Exception as e:
        logger.warning("Error recording equity point for %s: %s", account_id, e)
