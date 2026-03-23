"""Paper trading fill simulation.

Market orders fill immediately at current price.
Limit orders fill when price crosses the limit.
"""

from __future__ import annotations

import time
import uuid

from pnlclaw_types.trading import Fill, Order, OrderSide, OrderStatus, OrderType

# Default fee rate (0.1% — typical exchange maker/taker fee)
DEFAULT_FEE_RATE = 0.001


def try_fill(
    order: Order,
    current_price: float,
    *,
    fee_rate: float = DEFAULT_FEE_RATE,
) -> Fill | None:
    """Attempt to fill an order at the current price.

    For market orders: fill immediately at current_price.
    For limit orders: fill only if price condition is met:
      - BUY limit: current_price <= order.price
      - SELL limit: current_price >= order.price

    Returns a Fill object if the order can be executed, None otherwise.
    Does NOT mutate the order — caller is responsible for updating order state.

    Args:
        order: The order to attempt filling.
        current_price: Current market price.
        fee_rate: Fee as a fraction of trade value (default 0.1%).

    Returns:
        Fill if executable, None otherwise.
    """
    if order.status not in (OrderStatus.ACCEPTED, OrderStatus.PARTIAL):
        return None

    fill_price = _get_fill_price(order, current_price)
    if fill_price is None:
        return None

    remaining = order.quantity - order.filled_quantity
    if remaining <= 0:
        return None

    fill_quantity = remaining
    trade_value = fill_price * fill_quantity
    fee = trade_value * fee_rate

    return Fill(
        id=f"fill-{uuid.uuid4().hex[:8]}",
        order_id=order.id,
        price=fill_price,
        quantity=fill_quantity,
        fee=fee,
        fee_currency="USDT",
        timestamp=int(time.time() * 1000),
    )


def _get_fill_price(order: Order, current_price: float) -> float | None:
    """Determine the fill price, or None if conditions aren't met."""
    if order.type == OrderType.MARKET:
        return current_price

    if order.type == OrderType.LIMIT:
        if order.price is None:
            return None
        if order.side == OrderSide.BUY and current_price <= order.price:
            return order.price
        if order.side == OrderSide.SELL and current_price >= order.price:
            return order.price
        return None

    if order.type == OrderType.STOP_MARKET:
        if order.stop_price is None:
            return None
        if order.side == OrderSide.BUY and current_price >= order.stop_price:
            return current_price
        if order.side == OrderSide.SELL and current_price <= order.stop_price:
            return current_price
        return None

    if order.type == OrderType.STOP_LIMIT:
        if order.stop_price is None or order.price is None:
            return None
        triggered = (
            (order.side == OrderSide.BUY and current_price >= order.stop_price)
            or (order.side == OrderSide.SELL and current_price <= order.stop_price)
        )
        if not triggered:
            return None
        if order.side == OrderSide.BUY and current_price <= order.price:
            return order.price
        if order.side == OrderSide.SELL and current_price >= order.price:
            return order.price
        return None

    return None
