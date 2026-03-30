"""Paper order management with strict state machine transitions.

State machine:
    created → accepted → partial → filled
                       ↘ cancelled
             ↘ rejected
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from pnlclaw_types.common import Symbol
from pnlclaw_types.trading import MarginMode, Order, OrderSide, OrderStatus, OrderType, PositionSide

# ---------------------------------------------------------------------------
# Legal state transitions
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {OrderStatus.ACCEPTED, OrderStatus.REJECTED},
    OrderStatus.ACCEPTED: {OrderStatus.PARTIAL, OrderStatus.FILLED, OrderStatus.CANCELLED},
    OrderStatus.PARTIAL: {OrderStatus.FILLED, OrderStatus.CANCELLED},
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
}


class InvalidOrderTransition(Exception):
    """Raised when attempting an illegal order state transition."""

    def __init__(self, current: OrderStatus, target: OrderStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition from {current.value} to {target.value}")


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    """Check if a state transition is legal."""
    return target in _VALID_TRANSITIONS.get(current, set())


# ---------------------------------------------------------------------------
# PaperOrderManager
# ---------------------------------------------------------------------------


class PaperOrderManager:
    """Manages order lifecycle for a paper trading account."""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        # account_id → list of order_ids
        self._account_orders: dict[str, list[str]] = {}

    def place_order(
        self,
        account_id: str,
        *,
        symbol: Symbol,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: float | None = None,
        stop_price: float | None = None,
        leverage: int = 1,
        margin_mode: MarginMode = MarginMode.CROSS,
        pos_side: PositionSide = PositionSide.NET,
        reduce_only: bool = False,
    ) -> Order:
        """Create and accept a new order.

        Order starts as CREATED then immediately transitions to ACCEPTED.
        Quantity is in USDT (quote currency) for derivatives.
        """
        now_ms = int(time.time() * 1000)
        order_id = f"ord-{uuid.uuid4().hex[:8]}"

        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            type=order_type,
            status=OrderStatus.CREATED,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            filled_quantity=0.0,
            avg_fill_price=None,
            leverage=leverage,
            margin_mode=margin_mode,
            pos_side=pos_side,
            reduce_only=reduce_only,
            created_at=now_ms,
            updated_at=now_ms,
        )

        self._orders[order_id] = order
        self._account_orders.setdefault(account_id, []).append(order_id)

        # Auto-accept
        self._transition(order, OrderStatus.ACCEPTED)
        return order

    def cancel_order(self, order_id: str) -> Order:
        """Cancel an order. Raises if transition is illegal."""
        order = self._get_or_raise(order_id)
        self._transition(order, OrderStatus.CANCELLED)
        return order

    def reject_order(self, order_id: str, reason: str = "") -> Order:
        """Reject an order (only from CREATED state)."""
        order = self._get_or_raise(order_id)
        self._transition(order, OrderStatus.REJECTED)
        return order

    def get_order(self, order_id: str) -> Order | None:
        """Get an order by ID."""
        return self._orders.get(order_id)

    def get_orders(
        self,
        account_id: str,
        status: OrderStatus | None = None,
    ) -> list[Order]:
        """Get orders for an account, optionally filtered by status."""
        order_ids = self._account_orders.get(account_id, [])
        orders = [self._orders[oid] for oid in order_ids if oid in self._orders]
        if status is not None:
            orders = [o for o in orders if o.status == status]
        return orders

    def update_fill(
        self,
        order_id: str,
        fill_quantity: float,
        fill_price: float,
    ) -> Order:
        """Record a fill against an order, updating status accordingly.

        Updates filled_quantity, avg_fill_price, and transitions:
          - To PARTIAL if partially filled
          - To FILLED if fully filled
        """
        order = self._get_or_raise(order_id)

        if order.status not in (OrderStatus.ACCEPTED, OrderStatus.PARTIAL):
            raise InvalidOrderTransition(order.status, OrderStatus.PARTIAL)

        # Calculate new weighted average
        old_total = (order.avg_fill_price or 0.0) * order.filled_quantity
        new_total = old_total + fill_price * fill_quantity
        new_filled = order.filled_quantity + fill_quantity
        order.avg_fill_price = new_total / new_filled if new_filled > 0 else 0.0
        order.filled_quantity = new_filled
        order.updated_at = int(time.time() * 1000)

        if new_filled >= order.quantity:
            self._transition(order, OrderStatus.FILLED)
        elif order.status == OrderStatus.ACCEPTED:
            self._transition(order, OrderStatus.PARTIAL)

        return order

    def get_open_orders(self, account_id: str | None = None) -> list[Order]:
        """Get all orders that can still be filled (ACCEPTED or PARTIAL)."""
        open_statuses = {OrderStatus.ACCEPTED, OrderStatus.PARTIAL}
        if account_id:
            return [o for o in self.get_orders(account_id) if o.status in open_statuses]
        return [o for o in self._orders.values() if o.status in open_statuses]

    def clear_orders(self, account_id: str) -> None:
        """Remove all orders for an account."""
        order_ids = self._account_orders.pop(account_id, [])
        for oid in order_ids:
            self._orders.pop(oid, None)

    # -- internal --------------------------------------------------------------

    def _get_or_raise(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"Order {order_id} not found")
        return order

    def _transition(self, order: Order, target: OrderStatus) -> None:
        if not can_transition(order.status, target):
            raise InvalidOrderTransition(order.status, target)
        order.status = target
        order.updated_at = int(time.time() * 1000)

    # -- serialization hooks ---------------------------------------------------

    def get_all_data(self) -> dict[str, Any]:
        """Return internal state for serialization."""
        return {
            "orders": {k: v.model_dump() for k, v in self._orders.items()},
            "account_orders": dict(self._account_orders),
        }

    def load_data(self, data: dict[str, Any]) -> None:
        """Load state from deserialized data."""
        self._orders = {k: Order.model_validate(v) for k, v in data.get("orders", {}).items()}
        self._account_orders = data.get("account_orders", {})
