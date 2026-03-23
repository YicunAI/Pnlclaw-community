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
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
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
    ) -> Order:
        order = self._order_mgr.place_order(
            account_id=account_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
        )
        await self._fire_order_update(order)

        # For market orders, attempt immediate fill if we have a price
        if order_type == OrderType.MARKET and symbol in self._last_prices:
            await self._try_fill_order(order, self._last_prices[symbol])

        return order

    async def cancel_order(self, order_id: str) -> Order:
        self._order_mgr.cancel_order(order_id)
        order = self._order_mgr.get_order(order_id)
        if order is not None:
            await self._fire_order_update(order)
            return order
        raise ValueError(f"Order {order_id} not found")

    async def get_orders(
        self, account_id: str, *, status: OrderStatus | None = None
    ) -> list[Order]:
        return self._order_mgr.get_orders(account_id, status=status)

    async def get_open_orders(self, account_id: str) -> list[Order]:
        return self._order_mgr.get_open_orders(account_id)

    async def get_positions(self, account_id: str) -> list[Position]:
        return self._position_mgr.get_open_positions(account_id)

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

    # ------------------------------------------------------------------
    # Price feed integration
    # ------------------------------------------------------------------

    async def on_price_tick(self, symbol: str, price: float) -> None:
        """Called on every real-time price update.

        Scans all open orders for the symbol and attempts to fill them.
        Also updates unrealized PnL for open positions.
        """
        self._last_prices[symbol] = price

        open_orders = self._order_mgr.get_open_orders()
        for order in open_orders:
            if order.symbol == symbol:
                await self._try_fill_order(order, price)

    # ------------------------------------------------------------------
    # Internal fill logic
    # ------------------------------------------------------------------

    async def _try_fill_order(self, order: Order, current_price: float) -> None:
        fill = try_fill(order, current_price, fee_rate=self._fee_rate)
        if fill is None:
            return

        self._order_mgr.update_fill(order.id, fill.quantity, fill.price)
        self._fills.append(fill)

        updated_order = self._order_mgr.get_order(order.id)
        if updated_order:
            await self._fire_order_update(updated_order)

        await self._fire_fill(fill)

        # Determine account_id from order manager's internal mapping
        account_id = self._get_order_account(order.id)

        pos, realized_pnl = self._position_mgr.apply_fill_with_symbol(
            account_id=account_id,
            symbol=order.symbol,
            fill=fill,
            side=order.side,
        )
        await self._fire_position_update(pos)

        # Update account balance with realized PnL minus fees
        net_pnl = realized_pnl - fill.fee
        if net_pnl != 0:
            self._account_mgr.update_balance(account_id, net_pnl)

        balances = await self.get_balances(account_id)
        await self._fire_balance_update(balances)

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

    async def _fire_position_update(self, position: Position) -> None:
        for cb in self._on_position_update_cbs:
            await self._invoke(cb, position)

    async def _fire_balance_update(self, balances: list[BalanceUpdate]) -> None:
        for cb in self._on_balance_update_cbs:
            await self._invoke(cb, balances)

    @staticmethod
    async def _invoke(callback: Callable[..., Any], *args: Any) -> None:
        result = callback(*args)
        if inspect.isawaitable(result):
            await result
