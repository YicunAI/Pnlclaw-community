"""Paper execution engine — simulates trading using real market prices.

Implements the ExecutionEngine protocol for paper (simulated) trading:
- Receives real-time ticker prices from MarketDataService EventBus
- Scans open orders on every price tick and attempts to fill them
- Updates positions and balances on fill
- Fires event callbacks for order/fill/position/balance changes
"""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Callable
from typing import Any

from pnlclaw_paper.accounts import AccountManager
from pnlclaw_paper.fills import try_fill
from pnlclaw_paper.orders import PaperOrderManager
from pnlclaw_paper.positions import PositionManager
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

DEFAULT_ACCOUNT_ID = "paper-default"
DEFAULT_INITIAL_BALANCE = 100_000.0


class PaperExecutionEngine:
    """ExecutionEngine implementation for paper (simulated) trading.

    Driven by real market prices — each price tick scans all open orders
    and simulates fills when price conditions are met.
    """

    def __init__(
        self,
        *,
        default_account_id: str = DEFAULT_ACCOUNT_ID,
        initial_balance: float = DEFAULT_INITIAL_BALANCE,
        fee_rate: float = 0.001,
    ) -> None:
        self._account_mgr = AccountManager()
        self._order_mgr = PaperOrderManager()
        self._position_mgr = PositionManager()
        self._fills: list[Fill] = []
        self._fee_rate = fee_rate
        self._default_account_id = default_account_id
        self._initial_balance = initial_balance

        self._last_prices: dict[str, float] = {}

        self._on_order_update_cbs: list[Callable[[Order], Any]] = []
        self._on_fill_cbs: list[Callable[[Fill], Any]] = []
        self._on_position_update_cbs: list[Callable[[Position], Any]] = []
        self._on_balance_update_cbs: list[Callable[[list[BalanceUpdate]], Any]] = []
        self._on_position_update_scoped_cbs: list[Callable[[str, Position], Any]] = []
        self._on_balance_update_scoped_cbs: list[Callable[[str, list[BalanceUpdate]], Any]] = []

    def _get_fee_rates(self, account_id: str) -> tuple[float, float]:
        """Return (maker_fee_rate, taker_fee_rate) for the given account."""
        acct = self._account_mgr.get_account(account_id)
        if acct is not None:
            return acct.maker_fee_rate, acct.taker_fee_rate
        return 0.0002, 0.0005

    def update_fee_rates(self, account_id: str, maker: float, taker: float) -> None:
        """Update maker/taker fee rates for an account at runtime."""
        acct = self._account_mgr.get_account(account_id)
        if acct is not None:
            acct.maker_fee_rate = maker
            acct.taker_fee_rate = taker
            acct.updated_at = int(time.time() * 1000)

    def compute_equity(self, account_id: str) -> float:
        """Compute account equity = wallet_balance + unrealized PnL.

        wallet_balance = initial_balance + total_realized_pnl - total_fee
        This is the OKX model: margin locked in positions is still part of
        the wallet balance, so equity reflects the true total account value.
        """
        acct = self._account_mgr.get_account(account_id)
        if acct is None:
            return 0.0
        wallet_balance = acct.initial_balance + acct.total_realized_pnl - acct.total_fee
        positions = self._position_mgr.get_open_positions(account_id)
        unrealized = sum(p.unrealized_pnl for p in positions)
        return wallet_balance + unrealized

    # ------------------------------------------------------------------
    # ExecutionEngine interface
    # ------------------------------------------------------------------

    @property
    def mode(self) -> ExecutionMode:
        return ExecutionMode.PAPER

    @property
    def exchange(self) -> str:
        return "paper"

    async def start(self) -> None:
        if self._account_mgr.get_account(self._default_account_id) is None:
            self._account_mgr.create_account(
                name="Default Paper Account",
                initial_balance=self._initial_balance,
            )
            acct = self._account_mgr.list_accounts()[-1]
            # Reassign the ID to match the configured default
            self._account_mgr._accounts.pop(acct.id, None)
            acct.id = self._default_account_id
            self._account_mgr._accounts[acct.id] = acct
        logger.info("PaperExecutionEngine started (balance=%.2f)", self._initial_balance)

    async def stop(self) -> None:
        logger.info("PaperExecutionEngine stopped")

    async def place_order(
        self,
        *,
        account_id: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: float | None = None,
        stop_price: float | None = None,
        leverage: int = 1,
        margin_mode: MarginMode = MarginMode.CROSS,
        pos_side: PositionSide = PositionSide.NET,
        reduce_only: bool = False,
        mark_price: float | None = None,
        signal_timestamp_ms: int | None = None,
    ) -> Order:
        """Place order. ``quantity`` is in USDT notional.

        For market orders, ``mark_price`` (from the frontend ticker) is used as
        the fill price when the engine's internal price cache has no entry for
        the symbol.  This guarantees immediate fill for market orders.

        Margin check: required margin = quantity / leverage (skipped for reduce_only).
        """
        if not reduce_only:
            required_margin = quantity / leverage
            acct = self._account_mgr.get_account(account_id)
            if acct is not None and acct.current_balance < required_margin:
                raise ValueError(
                    f"Insufficient margin: need {required_margin:.2f} USDT "
                    f"but only {acct.current_balance:.2f} available"
                )

        order = self._order_mgr.place_order(
            account_id=account_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            leverage=leverage,
            margin_mode=margin_mode,
            pos_side=pos_side,
            reduce_only=reduce_only,
        )
        await self._fire_order_update(order)

        if order_type == OrderType.MARKET:
            fill_price = self._resolve_price(symbol, price)
            if fill_price is None and mark_price is not None and mark_price > 0:
                fill_price = mark_price
                self._last_prices[symbol] = mark_price
                logger.info(
                    "Using frontend mark_price %.2f for %s (no cached price)",
                    mark_price,
                    symbol,
                )
            if fill_price is not None:
                try:
                    await self._try_fill_order(order, fill_price, timestamp_ms=signal_timestamp_ms)
                except Exception:
                    logger.error(
                        "Fill failed for market order %s, forcing fill",
                        order.id,
                        exc_info=True,
                    )
                    self._force_fill_market_order(order, fill_price)

            if order.status not in (OrderStatus.FILLED, OrderStatus.PARTIAL):
                logger.warning(
                    "Market order %s still not filled (status=%s), forcing fill at %.2f",
                    order.id,
                    order.status.value,
                    fill_price or mark_price or 0,
                )
                final_price = fill_price or mark_price
                if final_price and final_price > 0:
                    self._force_fill_market_order(order, final_price)

        return order

    def _force_fill_market_order(self, order: Order, fill_price: float) -> None:
        """Last-resort fill: directly mutate order to FILLED status.

        Used when normal fill pipeline fails due to callback errors or other
        transient issues.  Ensures market orders never stay in ACCEPTED state.
        """
        if order.status in (OrderStatus.FILLED,):
            return
        remaining = order.quantity - order.filled_quantity
        if remaining <= 0:
            return

        account_id = self._get_order_account(order.id)
        maker_rate, taker_rate = self._get_fee_rates(account_id)
        effective_rate = taker_rate
        fee = remaining * effective_rate
        now_ms = int(time.time() * 1000)

        order.filled_quantity = order.quantity
        order.avg_fill_price = fill_price
        order.status = OrderStatus.FILLED
        order.updated_at = now_ms

        is_close = getattr(order, "reduce_only", False)

        fill = Fill(
            id=f"fill-{order.id[-8:]}",
            order_id=order.id,
            price=fill_price,
            quantity=remaining,
            fee=fee,
            fee_currency="USDT",
            fee_rate=effective_rate,
            exec_type="taker",
            side=order.side.value if hasattr(order.side, "value") else str(order.side),
            pos_side=order.pos_side.value if hasattr(order.pos_side, "value") else str(order.pos_side),
            symbol=order.symbol,
            leverage=order.leverage,
            reduce_only=is_close,
            timestamp=now_ms,
        )

        acct = self._account_mgr.get_account(account_id)
        balance_for_liq = acct.current_balance if acct else None

        try:
            pos, realized_pnl = self._position_mgr.apply_fill_with_symbol(
                account_id=account_id,
                symbol=order.symbol,
                fill=fill,
                side=order.side,
                leverage=order.leverage,
                margin_mode=order.margin_mode,
                pos_side=order.pos_side,
                available_balance=balance_for_liq,
            )

            fill.realized_pnl = realized_pnl

            if is_close:
                self._account_mgr.update_balance(account_id, fill.quantity / order.leverage - fee)
            else:
                self._account_mgr.update_balance(account_id, -(fill.quantity / order.leverage) - fee)

            if realized_pnl != 0:
                self._account_mgr.update_balance(account_id, realized_pnl)

            if acct is not None:
                acct.total_realized_pnl += realized_pnl
                acct.total_fee += fee
        except Exception:
            logger.error("Force-fill position/balance update failed", exc_info=True)

        self._fills.append(fill)

    def _resolve_price(self, symbol: str, limit_price: float | None = None) -> float | None:
        """Find a usable price for *symbol* from cached ticks or limit price."""
        if symbol in self._last_prices:
            return self._last_prices[symbol]
        normalized = symbol.upper().replace("-SWAP", "").replace("-", "/")
        if normalized in self._last_prices:
            return self._last_prices[normalized]
        for key, val in self._last_prices.items():
            if key.replace("/", "-").replace("-SWAP", "") == symbol.replace("/", "-").replace("-SWAP", ""):
                return val
        return limit_price

    async def cancel_order(self, order_id: str) -> Order:
        self._order_mgr.cancel_order(order_id)
        order = self._order_mgr.get_order(order_id)
        if order is not None:
            await self._fire_order_update(order)
            return order
        raise ValueError(f"Order {order_id} not found")

    async def get_orders(self, account_id: str, *, status: OrderStatus | None = None) -> list[Order]:
        return self._order_mgr.get_orders(account_id, status=status)

    async def get_open_orders(self, account_id: str) -> list[Order]:
        return self._order_mgr.get_open_orders(account_id)

    async def get_positions(self, account_id: str) -> list[Position]:
        return self._position_mgr.get_open_positions(account_id)

    def delete_account(self, account_id: str) -> bool:
        """Delete an account and its history. Returns True if found."""
        exists = self._account_mgr.delete_account(account_id)
        if exists:
            # Cleanup related data in orders/positions managers
            self._order_mgr.clear_orders(account_id)
            self._position_mgr.clear_positions(account_id)
            # Filter in-memory fills
            self._fills = [f for f in self._fills if not self._fill_belongs_to(f, account_id)]
            logger.info("Deleted paper account %s and cleaned up history", account_id)
        return exists

    def reset_account(self, account_id: str) -> bool:
        """Reset an account's balance and clear its history."""
        success = self._account_mgr.reset_account(account_id) is not None
        if success:
            # Cleanup related data
            self._order_mgr.clear_orders(account_id)
            self._position_mgr.clear_positions(account_id)
            self._fills = [f for f in self._fills if not self._fill_belongs_to(f, account_id)]
            logger.info("Reset paper account %s and cleared history", account_id)
        return success

    async def get_balances(self, account_id: str) -> list[BalanceUpdate]:
        acct = self._account_mgr.get_account(account_id)
        if acct is None:
            return []
        return [
            BalanceUpdate(
                exchange="paper",
                asset="USDT",
                free=acct.current_balance,
                locked=0.0,
                timestamp=int(time.time() * 1000),
            )
        ]

    async def get_fills(self, account_id: str) -> list[Fill]:
        return [f for f in self._fills if self._fill_belongs_to(f, account_id)]

    # ------------------------------------------------------------------
    # Event callback registration
    # ------------------------------------------------------------------

    def on_order_update(self, callback: Callable[[Order], Any]) -> None:
        self._on_order_update_cbs.append(callback)

    def on_fill(self, callback: Callable[[Fill], Any]) -> None:
        self._on_fill_cbs.append(callback)

    def on_position_update(self, callback: Callable[[Position], Any]) -> None:
        self._on_position_update_cbs.append(callback)

    def on_balance_update(self, callback: Callable[[list[BalanceUpdate]], Any]) -> None:
        self._on_balance_update_cbs.append(callback)

    def on_position_update_scoped(self, callback: Callable[[str, Position], Any]) -> None:
        """Register a callback that receives (account_id, position) for proper routing."""
        self._on_position_update_scoped_cbs.append(callback)

    def on_balance_update_scoped(self, callback: Callable[[str, list[BalanceUpdate]], Any]) -> None:
        """Register a callback that receives (account_id, balances) for proper routing."""
        self._on_balance_update_scoped_cbs.append(callback)

    # ------------------------------------------------------------------
    # Price feed integration
    # ------------------------------------------------------------------

    @staticmethod
    def _symbols_match(a: str, b: str) -> bool:
        """Check if two symbol strings refer to the same instrument."""
        if a == b:
            return True
        norm_a = a.upper().replace("-SWAP", "").replace("/", "-")
        norm_b = b.upper().replace("-SWAP", "").replace("/", "-")
        return norm_a == norm_b

    async def on_price_tick(self, symbol: str, price: float) -> None:
        """Called on every real-time price update.

        Scans all open orders for the symbol and attempts to fill them.
        Also updates unrealized PnL for open positions.
        """
        self._last_prices[symbol] = price

        for account in self._account_mgr.list_accounts():
            updated_positions = self._position_mgr.update_unrealized_pnl(account.id, symbol, price)
            for pos in updated_positions:
                await self._fire_position_update(pos, account_id=account.id)

        open_orders = self._order_mgr.get_open_orders()
        for order in open_orders:
            if self._symbols_match(order.symbol, symbol):
                await self._try_fill_order(order, price)

    # ------------------------------------------------------------------
    # Internal fill logic
    # ------------------------------------------------------------------

    async def _try_fill_order(
        self,
        order: Order,
        current_price: float,
        *,
        timestamp_ms: int | None = None,
    ) -> None:
        account_id = self._get_order_account(order.id)
        maker_rate, taker_rate = self._get_fee_rates(account_id)

        fill = try_fill(
            order,
            current_price,
            maker_fee_rate=maker_rate,
            taker_fee_rate=taker_rate,
            timestamp_ms=timestamp_ms,
        )
        if fill is None:
            return

        self._order_mgr.update_fill(order.id, fill.quantity, fill.price)

        is_close = getattr(order, "reduce_only", False)
        acct = self._account_mgr.get_account(account_id)
        balance_for_liq = acct.current_balance if acct else None

        pos, realized_pnl = self._position_mgr.apply_fill_with_symbol(
            account_id=account_id,
            symbol=order.symbol,
            fill=fill,
            side=order.side,
            leverage=order.leverage,
            margin_mode=order.margin_mode,
            pos_side=order.pos_side,
            available_balance=balance_for_liq,
        )

        fill.realized_pnl = realized_pnl
        fill.side = order.side.value if hasattr(order.side, "value") else str(order.side)
        fill.pos_side = order.pos_side.value if hasattr(order.pos_side, "value") else str(order.pos_side)
        fill.symbol = order.symbol
        fill.leverage = order.leverage
        fill.reduce_only = is_close
        self._fills.append(fill)

        if acct is not None:
            acct.total_realized_pnl += realized_pnl
            acct.total_fee += fill.fee

        updated_order = self._order_mgr.get_order(order.id)
        if updated_order:
            await self._fire_order_update(updated_order)
        await self._fire_fill(fill)
        await self._fire_position_update(pos, account_id=account_id)

        if is_close:
            released_margin = fill.quantity / order.leverage
            self._account_mgr.update_balance(account_id, released_margin - fill.fee)
        else:
            margin_used = fill.quantity / order.leverage
            self._account_mgr.update_balance(account_id, -margin_used - fill.fee)

        if realized_pnl != 0:
            self._account_mgr.update_balance(account_id, realized_pnl)

        balances = await self.get_balances(account_id)
        await self._fire_balance_update(balances, account_id=account_id)

    def _get_order_account(self, order_id: str) -> str:
        """Look up the account_id for a given order."""
        for acct_id in [a.id for a in self._account_mgr.list_accounts()]:
            orders = self._order_mgr.get_orders(acct_id)
            for o in orders:
                if o.id == order_id:
                    return acct_id
        return self._default_account_id

    def _fill_belongs_to(self, fill: Fill, account_id: str) -> bool:
        orders = self._order_mgr.get_orders(account_id)
        order_ids = {o.id for o in orders}
        return fill.order_id in order_ids

    # ------------------------------------------------------------------
    # Event firing
    # ------------------------------------------------------------------

    async def _fire_order_update(self, order: Order) -> None:
        for cb in self._on_order_update_cbs:
            await self._invoke(cb, order)

    async def _fire_fill(self, fill: Fill) -> None:
        for cb in self._on_fill_cbs:
            await self._invoke(cb, fill)

    async def _fire_position_update(self, position: Position, account_id: str | None = None) -> None:
        for cb in self._on_position_update_cbs:
            await self._invoke(cb, position)
        if account_id is not None:
            for cb in self._on_position_update_scoped_cbs:
                await self._invoke(cb, account_id, position)

    async def _fire_balance_update(self, balances: list[BalanceUpdate], account_id: str | None = None) -> None:
        for cb in self._on_balance_update_cbs:
            await self._invoke(cb, balances)
        if account_id is not None:
            for cb in self._on_balance_update_scoped_cbs:
                await self._invoke(cb, account_id, balances)

    @staticmethod
    async def _invoke(callback: Callable[..., Any], *args: Any) -> None:
        result = callback(*args)
        if inspect.isawaitable(result):
            await result
