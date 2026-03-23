"""Tests for PaperExecutionEngine — fills, stop orders, price-driven execution."""

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


class TestPaperExecutionEngine:
    @pytest.mark.asyncio
    async def test_mode(self, engine: PaperExecutionEngine) -> None:
        assert engine.mode == ExecutionMode.PAPER
        assert engine.exchange == "paper"

    @pytest.mark.asyncio
    async def test_initial_balance(self, engine: PaperExecutionEngine) -> None:
        balances = await engine.get_balances(ACCOUNT)
        assert len(balances) == 1
        assert balances[0].asset == "USDT"
        assert balances[0].free == 100_000.0

    @pytest.mark.asyncio
    async def test_place_market_order_with_price(self, engine: PaperExecutionEngine) -> None:
        # Provide a price so market order fills immediately
        await engine.on_price_tick("BTC/USDT", 67000.0)

        order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )

        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 0.1

    @pytest.mark.asyncio
    async def test_place_limit_order_pending(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC/USDT", 67000.0)

        order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.1,
            price=60000.0,
        )

        # Price is above limit, so should not fill
        assert order.status in (OrderStatus.ACCEPTED, OrderStatus.CREATED)
        assert order.filled_quantity == 0.0

    @pytest.mark.asyncio
    async def test_limit_order_fills_on_price_tick(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC/USDT", 67000.0)

        order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.1,
            price=66000.0,
        )

        assert order.filled_quantity == 0.0

        # Price drops below limit
        await engine.on_price_tick("BTC/USDT", 65000.0)

        orders = await engine.get_orders(ACCOUNT)
        filled = [o for o in orders if o.id == order.id]
        assert len(filled) == 1
        assert filled[0].status == OrderStatus.FILLED
        assert filled[0].filled_quantity == 0.1

    @pytest.mark.asyncio
    async def test_stop_market_order(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC/USDT", 67000.0)

        order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            quantity=0.1,
            stop_price=65000.0,
        )

        # Price above stop, should not trigger
        await engine.on_price_tick("BTC/USDT", 66000.0)
        updated = await engine.get_orders(ACCOUNT, status=OrderStatus.FILLED)
        assert len(updated) == 0

        # Price drops below stop
        await engine.on_price_tick("BTC/USDT", 64000.0)
        updated = await engine.get_orders(ACCOUNT, status=OrderStatus.FILLED)
        assert len(updated) == 1
        assert updated[0].id == order.id

    @pytest.mark.asyncio
    async def test_cancel_order(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC/USDT", 67000.0)

        order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.1,
            price=60000.0,
        )

        cancelled = await engine.cancel_order(order.id)
        assert cancelled.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_position_after_fill(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC/USDT", 67000.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.5,
        )

        positions = await engine.get_positions(ACCOUNT)
        assert len(positions) >= 1
        btc_pos = next((p for p in positions if p.symbol == "BTC/USDT"), None)
        assert btc_pos is not None
        assert btc_pos.quantity == 0.5
        assert btc_pos.side == OrderSide.BUY

    @pytest.mark.asyncio
    async def test_fills_tracked(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC/USDT", 67000.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )

        fills = await engine.get_fills(ACCOUNT)
        assert len(fills) >= 1
        assert fills[0].price == 67000.0
        assert fills[0].quantity == 0.1

    @pytest.mark.asyncio
    async def test_event_callbacks_fired(self, engine: PaperExecutionEngine) -> None:
        order_events: list[Order] = []
        fill_events: list[Fill] = []
        position_events: list[Position] = []
        balance_events: list[list[BalanceUpdate]] = []

        engine.on_order_update(lambda o: order_events.append(o))
        engine.on_fill(lambda f: fill_events.append(f))
        engine.on_position_update(lambda p: position_events.append(p))
        engine.on_balance_update(lambda b: balance_events.append(b))

        await engine.on_price_tick("BTC/USDT", 67000.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )

        assert len(order_events) >= 1
        assert len(fill_events) >= 1
        assert len(position_events) >= 1
        assert len(balance_events) >= 1
