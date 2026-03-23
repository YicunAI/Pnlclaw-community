"""Tests for pnlclaw_backtest.broker."""

from pnlclaw_backtest.broker import SimulatedBroker
from pnlclaw_backtest.commissions import PercentageCommission
from pnlclaw_backtest.slippage import FixedSlippage
from pnlclaw_types.market import KlineEvent
from pnlclaw_types.trading import Order, OrderSide, OrderStatus, OrderType


def _make_kline(close: float = 100.0, low: float = 95.0, high: float = 105.0) -> KlineEvent:
    return KlineEvent(
        exchange="backtest",
        symbol="BTC/USDT",
        timestamp=1711000000000,
        interval="1h",
        open=98.0,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        closed=True,
    )


def _make_order(
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    quantity: float = 1.0,
    price: float | None = None,
) -> Order:
    return Order(
        id="test-ord-001",
        symbol="BTC/USDT",
        side=side,
        type=order_type,
        quantity=quantity,
        price=price,
        created_at=1711000000000,
        updated_at=1711000000000,
    )


class TestMarketOrder:
    def test_fills_at_close(self) -> None:
        broker = SimulatedBroker()
        order = _make_order()
        kline = _make_kline(close=67000.0)
        fill = broker.execute(order, kline)

        assert fill is not None
        assert fill.price == 67000.0
        assert fill.quantity == 1.0
        assert order.status == OrderStatus.FILLED

    def test_fills_with_slippage(self) -> None:
        broker = SimulatedBroker(slippage=FixedSlippage(bps=10))
        order = _make_order()
        kline = _make_kline(close=10000.0)
        fill = broker.execute(order, kline)

        assert fill is not None
        assert fill.price == 10000.0 * 1.001  # buy slips up

    def test_fills_with_commission(self) -> None:
        broker = SimulatedBroker(commission=PercentageCommission(rate=0.001))
        order = _make_order(quantity=2.0)
        kline = _make_kline(close=50000.0)
        fill = broker.execute(order, kline)

        assert fill is not None
        assert fill.fee == 50000.0 * 2.0 * 0.001


class TestLimitOrder:
    def test_buy_limit_triggered(self) -> None:
        broker = SimulatedBroker()
        order = _make_order(side=OrderSide.BUY, order_type=OrderType.LIMIT, price=96.0)
        kline = _make_kline(low=95.0)  # low <= 96 → triggered
        fill = broker.execute(order, kline)

        assert fill is not None
        assert fill.price == 96.0

    def test_buy_limit_not_triggered(self) -> None:
        broker = SimulatedBroker()
        order = _make_order(side=OrderSide.BUY, order_type=OrderType.LIMIT, price=90.0)
        kline = _make_kline(low=95.0)  # low > 90 → not triggered
        fill = broker.execute(order, kline)

        assert fill is None

    def test_sell_limit_triggered(self) -> None:
        broker = SimulatedBroker()
        order = _make_order(side=OrderSide.SELL, order_type=OrderType.LIMIT, price=104.0)
        kline = _make_kline(high=105.0)  # high >= 104 → triggered
        fill = broker.execute(order, kline)

        assert fill is not None
        assert fill.price == 104.0

    def test_sell_limit_not_triggered(self) -> None:
        broker = SimulatedBroker()
        order = _make_order(side=OrderSide.SELL, order_type=OrderType.LIMIT, price=110.0)
        kline = _make_kline(high=105.0)
        fill = broker.execute(order, kline)

        assert fill is None
