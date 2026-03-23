"""Simulated broker for backtesting.

Receives orders and simulates execution against the current kline bar.
Market orders fill at close (with slippage).  Limit orders fill if the
kline's price range reaches the limit price.
"""

from __future__ import annotations

import uuid

from pnlclaw_backtest.commissions import CommissionModel, NoCommission
from pnlclaw_backtest.slippage import NoSlippage, SlippageModel
from pnlclaw_types.market import KlineEvent
from pnlclaw_types.trading import Fill, Order, OrderStatus, OrderType


class SimulatedBroker:
    """Simulated broker that fills orders against kline data.

    Args:
        slippage: Slippage model applied to fill prices.
        commission: Commission model applied to each fill.
    """

    def __init__(
        self,
        slippage: SlippageModel | None = None,
        commission: CommissionModel | None = None,
    ) -> None:
        self._slippage = slippage or NoSlippage()
        self._commission = commission or NoCommission()

    def execute(self, order: Order, kline: KlineEvent) -> Fill | None:
        """Attempt to fill *order* against the given *kline* bar.

        Args:
            order: The order to execute.
            kline: The current kline bar providing price context.

        Returns:
            A ``Fill`` if the order is executed, or ``None`` if conditions
            are not met (e.g. limit price not reached).
        """
        if order.type == OrderType.MARKET:
            return self._fill_market(order, kline)
        if order.type == OrderType.LIMIT:
            return self._fill_limit(order, kline)
        return None

    def _fill_market(self, order: Order, kline: KlineEvent) -> Fill:
        """Market order — fill at close price with slippage."""
        raw_price = kline.close
        fill_price = self._slippage.apply(raw_price, order.side)
        fee = self._commission.calculate(fill_price, order.quantity)

        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.avg_fill_price = fill_price

        return Fill(
            id=f"fill-{uuid.uuid4().hex[:8]}",
            order_id=order.id,
            price=fill_price,
            quantity=order.quantity,
            fee=fee,
            timestamp=kline.timestamp,
        )

    def _fill_limit(self, order: Order, kline: KlineEvent) -> Fill | None:
        """Limit order — fill only if the kline range reaches the limit price.

        Buy limit: fills if kline.low <= order.price.
        Sell limit: fills if kline.high >= order.price.
        """
        if order.price is None:
            return None

        from pnlclaw_types.trading import OrderSide

        is_buy = order.side == OrderSide.BUY
        triggered = (is_buy and kline.low <= order.price) or (
            not is_buy and kline.high >= order.price
        )

        if not triggered:
            return None

        fill_price = self._slippage.apply(order.price, order.side)
        fee = self._commission.calculate(fill_price, order.quantity)

        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.avg_fill_price = fill_price

        return Fill(
            id=f"fill-{uuid.uuid4().hex[:8]}",
            order_id=order.id,
            price=fill_price,
            quantity=order.quantity,
            fee=fee,
            timestamp=kline.timestamp,
        )
