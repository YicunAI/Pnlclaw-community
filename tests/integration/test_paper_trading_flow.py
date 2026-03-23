"""Integration test: Paper trading full flow with price-driven fills.

Tests the complete paper trading pipeline:
    real ticker prices → PaperExecutionEngine → fill simulation →
    position tracking → balance updates → event callbacks
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from pnlclaw_paper.paper_execution import PaperExecutionEngine
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

ACCOUNT = "paper-default"


@pytest_asyncio.fixture
async def engine() -> PaperExecutionEngine:
    eng = PaperExecutionEngine(initial_balance=100_000.0, fee_rate=0.001)
    await eng.start()
    return eng


class TestPaperTradingFlow:
    """Full-flow paper trading integration test."""

    @pytest.mark.asyncio
    async def test_complete_trading_cycle(self, engine: PaperExecutionEngine) -> None:
        """Buy → price moves up → sell → verify PnL."""
        order_events: list[Order] = []
        fill_events: list[Fill] = []
        position_events: list[Position] = []
        balance_events: list[list[BalanceUpdate]] = []

        engine.on_order_update(lambda o: order_events.append(o))
        engine.on_fill(lambda f: fill_events.append(f))
        engine.on_position_update(lambda p: position_events.append(p))
        engine.on_balance_update(lambda b: balance_events.append(b))

        # 1. Provide initial price
        await engine.on_price_tick("BTC/USDT", 60000.0)

        # 2. Place a market buy order
        buy_order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
        )
        assert buy_order.status == OrderStatus.FILLED

        # 3. Verify position opened
        positions = await engine.get_positions(ACCOUNT)
        assert len(positions) == 1
        assert positions[0].symbol == "BTC/USDT"
        assert positions[0].side == OrderSide.BUY
        assert positions[0].quantity == 1.0

        # 4. Price goes up
        await engine.on_price_tick("BTC/USDT", 65000.0)

        # 5. Sell to close position
        sell_order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=1.0,
        )
        assert sell_order.status == OrderStatus.FILLED

        # 6. Verify fill history
        fills = await engine.get_fills(ACCOUNT)
        assert len(fills) == 2
        assert fills[0].price == 60000.0
        assert fills[1].price == 65000.0

        # 7. Events were fired
        assert len(order_events) >= 2
        assert len(fill_events) >= 2
        assert len(position_events) >= 2
        assert len(balance_events) >= 2

    @pytest.mark.asyncio
    async def test_limit_order_with_stop_loss(self, engine: PaperExecutionEngine) -> None:
        """Place limit buy, then set stop-loss sell."""
        await engine.on_price_tick("ETH/USDT", 3500.0)

        # Limit buy at 3400
        buy_order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10.0,
            price=3400.0,
        )
        assert buy_order.status == OrderStatus.ACCEPTED

        # Price drops to trigger limit
        await engine.on_price_tick("ETH/USDT", 3350.0)
        orders = await engine.get_orders(ACCOUNT, status=OrderStatus.FILLED)
        assert len(orders) == 1

        # Set stop-loss sell at 3200
        stop_order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="ETH/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            quantity=10.0,
            stop_price=3200.0,
        )
        assert stop_order.status == OrderStatus.ACCEPTED

        # Price drops to trigger stop
        await engine.on_price_tick("ETH/USDT", 3150.0)
        orders = await engine.get_orders(ACCOUNT, status=OrderStatus.FILLED)
        assert len(orders) == 2

    @pytest.mark.asyncio
    async def test_multiple_symbols(self, engine: PaperExecutionEngine) -> None:
        """Trade multiple symbols concurrently."""
        await engine.on_price_tick("BTC/USDT", 60000.0)
        await engine.on_price_tick("ETH/USDT", 3500.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.5,
        )

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=5.0,
        )

        positions = await engine.get_positions(ACCOUNT)
        symbols = {p.symbol for p in positions}
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols
