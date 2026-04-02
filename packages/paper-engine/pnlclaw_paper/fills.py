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
    maker_fee_rate: float | None = None,
    taker_fee_rate: float | None = None,
    timestamp_ms: int | None = None,
) -> Fill | None:
    """Attempt to fill an order at the current price.

    For market orders: fill immediately at current_price (taker fee).
    For limit orders: fill only if price condition is met (maker fee).

    When ``maker_fee_rate`` and ``taker_fee_rate`` are provided, the fee
    is determined by order type: market/stop -> taker, limit -> maker.
    Otherwise falls back to the single ``fee_rate``.

    ``timestamp_ms``: when provided (e.g. kline close time for strategy-driven
    fills), used as fill timestamp instead of wall-clock time.

    Returns a Fill object if the order can be executed, None otherwise.
    Does NOT mutate the order -- caller is responsible for updating order state.
    """
    if order.status not in (OrderStatus.ACCEPTED, OrderStatus.PARTIAL):
        return None

    fill_price = _get_fill_price(order, current_price)
    if fill_price is None:
        return None

    remaining = order.quantity - order.filled_quantity
    if remaining <= 0:
        return None

    is_taker = order.type in (OrderType.MARKET, OrderType.STOP_MARKET)
    if maker_fee_rate is not None and taker_fee_rate is not None:
        effective_rate = taker_fee_rate if is_taker else maker_fee_rate
    else:
        effective_rate = fee_rate

    fill_quantity = remaining
    fee = fill_quantity * effective_rate

    return Fill(
        id=f"fill-{uuid.uuid4().hex[:8]}",
        order_id=order.id,
        price=fill_price,
        quantity=fill_quantity,
        fee=fee,
        fee_currency="USDT",
        fee_rate=effective_rate,
        exec_type="taker" if is_taker else "maker",
        timestamp=timestamp_ms if timestamp_ms is not None else int(time.time() * 1000),
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
        triggered = (order.side == OrderSide.BUY and current_price >= order.stop_price) or (
            order.side == OrderSide.SELL and current_price <= order.stop_price
        )
        if not triggered:
            return None
        if order.side == OrderSide.BUY and current_price <= order.price:
            return order.price
        if order.side == OrderSide.SELL and current_price >= order.price:
            return order.price
        return None

    return None
