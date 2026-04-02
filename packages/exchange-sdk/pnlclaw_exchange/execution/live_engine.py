"""Live execution engine — real exchange trading with WS-first order tracking.

Places orders via REST and tracks their lifecycle primarily through private
WebSocket channels. REST is used as a fallback for reconciliation.

Architecture:
    place_order() → REST API → exchange
    exchange → Private WS → on_order_update callback → internal state update
    reconciliation → REST API (on reconnect / periodic)
"""

from __future__ import annotations

import inspect
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from pnlclaw_exchange.base.reconciliation import ReconciliationManager
from pnlclaw_exchange.trading import (
    OrderRequest,
    OrderResponse,
    TradingClient,
)
from pnlclaw_types.trading import (
    AccountSnapshot,
    BalanceUpdate,
    ExchangeOrderUpdate,
    ExecutionMode,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)

logger = logging.getLogger(__name__)


class LiveExecutionEngine:
    """ExecutionEngine implementation for live (real exchange) trading.

    WS-first architecture:
    - Orders placed via REST (TradingClient)
    - Status tracked via private WS (callbacks wired externally)
    - REST reconciliation as fallback (ReconciliationManager)
    - Local state maintained as client_order_id → Order mapping
    """

    def __init__(
        self,
        trading_client: TradingClient,
        *,
        reconciliation_interval_s: float = 300.0,
    ) -> None:
        self._client = trading_client
        self._reconciliation_interval = reconciliation_interval_s
        self._reconciliation: ReconciliationManager | None = None

        # Internal state
        self._orders: dict[str, Order] = {}
        self._fills: list[Fill] = []
        self._balances: list[BalanceUpdate] = []
        self._positions: list[Position] = []

        # Mapping: client_order_id → internal_order_id
        self._client_to_internal: dict[str, str] = {}
        # Mapping: exchange_order_id → internal_order_id
        self._exchange_to_internal: dict[str, str] = {}

        # Event callbacks
        self._on_order_update_cbs: list[Callable[[Order], Any]] = []
        self._on_fill_cbs: list[Callable[[Fill], Any]] = []
        self._on_position_update_cbs: list[Callable[[Position], Any]] = []
        self._on_balance_update_cbs: list[Callable[[list[BalanceUpdate]], Any]] = []

    # ------------------------------------------------------------------
    # ExecutionEngine interface
    # ------------------------------------------------------------------

    @property
    def mode(self) -> ExecutionMode:
        return ExecutionMode.LIVE

    @property
    def exchange(self) -> str:
        return self._client.exchange_name

    async def start(self) -> None:
        self._reconciliation = ReconciliationManager(
            self._client,
            on_snapshot=self._handle_reconciliation_snapshot,
            on_orders=self._handle_reconciliation_orders,
        )
        await self._reconciliation.start_periodic(self._reconciliation_interval)

        # Initial reconciliation
        await self._reconciliation.reconcile_on_reconnect()
        logger.info("LiveExecutionEngine started for %s", self.exchange)

    async def stop(self) -> None:
        if self._reconciliation:
            await self._reconciliation.stop()
        logger.info("LiveExecutionEngine stopped for %s", self.exchange)

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
        client_order_id = f"pnlclaw-{uuid.uuid4().hex[:12]}"
        internal_id = f"live-{uuid.uuid4().hex[:8]}"
        ts = int(time.time() * 1000)

        request = OrderRequest(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            client_order_id=client_order_id,
        )

        response = await self._client.place_order(request)

        order = Order(
            id=internal_id,
            symbol=symbol,
            side=side,
            type=order_type,
            status=response.status,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            filled_quantity=response.filled_quantity,
            avg_fill_price=response.avg_fill_price,
            created_at=ts,
            updated_at=ts,
        )

        self._orders[internal_id] = order
        self._client_to_internal[client_order_id] = internal_id
        if response.order_id:
            self._exchange_to_internal[response.order_id] = internal_id

        await self._fire_order_update(order)
        return order

    async def cancel_order(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"Order {order_id} not found")

        exchange_oid = self._find_exchange_order_id(order_id)
        if exchange_oid:
            await self._client.cancel_order(symbol=order.symbol, order_id=exchange_oid)

        order.status = OrderStatus.CANCELLED
        order.updated_at = int(time.time() * 1000)
        await self._fire_order_update(order)
        return order

    async def get_orders(self, account_id: str, *, status: OrderStatus | None = None) -> list[Order]:
        orders = list(self._orders.values())
        if status is not None:
            orders = [o for o in orders if o.status == status]
        return orders

    async def get_open_orders(self, account_id: str) -> list[Order]:
        terminal = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}
        return [o for o in self._orders.values() if o.status not in terminal]

    async def get_positions(self, account_id: str) -> list[Position]:
        return list(self._positions)

    async def get_balances(self, account_id: str) -> list[BalanceUpdate]:
        return list(self._balances)

    async def get_fills(self, account_id: str) -> list[Fill]:
        return list(self._fills)

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
    # WS event handlers — wire these to the private WS client
    # ------------------------------------------------------------------

    async def handle_exchange_order_update(self, update: ExchangeOrderUpdate) -> None:
        """Process a real-time order update from the exchange private WS.

        This is the PRIMARY path for order tracking.
        """
        internal_id = self._exchange_to_internal.get(update.exchange_order_id) or self._client_to_internal.get(
            update.client_order_id or ""
        )

        status_map = {
            "NEW": OrderStatus.ACCEPTED,
            "PARTIALLY_FILLED": OrderStatus.PARTIAL,
            "FILLED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.CANCELLED,
        }

        if internal_id and internal_id in self._orders:
            order = self._orders[internal_id]
            order.status = status_map.get(update.status, order.status)
            order.filled_quantity = update.filled_quantity
            order.avg_fill_price = update.avg_fill_price if update.avg_fill_price > 0 else order.avg_fill_price
            order.updated_at = update.timestamp
            await self._fire_order_update(order)
        else:
            # Order from external source — track it
            internal_id = f"ext-{uuid.uuid4().hex[:8]}"
            order = Order(
                id=internal_id,
                symbol=update.symbol,
                side=update.side,
                type=self._map_order_type(update.order_type),
                status=status_map.get(update.status, OrderStatus.ACCEPTED),
                quantity=update.quantity,
                filled_quantity=update.filled_quantity,
                avg_fill_price=update.avg_fill_price if update.avg_fill_price > 0 else None,
                created_at=update.timestamp,
                updated_at=update.timestamp,
            )
            self._orders[internal_id] = order
            self._exchange_to_internal[update.exchange_order_id] = internal_id
            if update.client_order_id:
                self._client_to_internal[update.client_order_id] = internal_id
            await self._fire_order_update(order)

        # Create fill if there was a new execution
        if update.last_fill_quantity > 0:
            fill = Fill(
                id=f"fill-{uuid.uuid4().hex[:8]}",
                order_id=internal_id,
                price=update.last_fill_price,
                quantity=update.last_fill_quantity,
                fee=update.commission,
                fee_currency=update.commission_asset or "USDT",
                timestamp=update.timestamp,
            )
            self._fills.append(fill)
            await self._fire_fill(fill)

    async def handle_balance_update(self, updates: list[BalanceUpdate]) -> None:
        """Process balance updates from the exchange private WS."""
        for upd in updates:
            existing = next((b for b in self._balances if b.asset == upd.asset), None)
            if existing:
                self._balances.remove(existing)
            self._balances.append(upd)
        await self._fire_balance_update(self._balances)

    # ------------------------------------------------------------------
    # Reconciliation handlers
    # ------------------------------------------------------------------

    async def _handle_reconciliation_snapshot(self, snapshot: AccountSnapshot) -> None:
        self._balances = list(snapshot.balances)
        await self._fire_balance_update(self._balances)

    async def _handle_reconciliation_orders(self, orders: list[OrderResponse]) -> None:
        for resp in orders:
            exchange_oid = resp.order_id
            if exchange_oid not in self._exchange_to_internal:
                internal_id = f"recon-{uuid.uuid4().hex[:8]}"
                order = Order(
                    id=internal_id,
                    symbol=resp.symbol,
                    side=resp.side,
                    type=resp.order_type,
                    status=resp.status,
                    quantity=resp.quantity,
                    filled_quantity=resp.filled_quantity,
                    price=resp.price,
                    avg_fill_price=resp.avg_fill_price,
                    created_at=resp.timestamp,
                    updated_at=resp.timestamp,
                )
                self._orders[internal_id] = order
                self._exchange_to_internal[exchange_oid] = internal_id
                if resp.client_order_id:
                    self._client_to_internal[resp.client_order_id] = internal_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_exchange_order_id(self, internal_id: str) -> str | None:
        for eid, iid in self._exchange_to_internal.items():
            if iid == internal_id:
                return eid
        return None

    @staticmethod
    def _map_order_type(exchange_type: str) -> OrderType:
        mapping = {
            "LIMIT": OrderType.LIMIT,
            "MARKET": OrderType.MARKET,
            "STOP_LOSS": OrderType.STOP_MARKET,
            "STOP_LOSS_LIMIT": OrderType.STOP_LIMIT,
            "limit": OrderType.LIMIT,
            "market": OrderType.MARKET,
        }
        return mapping.get(exchange_type, OrderType.MARKET)

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
