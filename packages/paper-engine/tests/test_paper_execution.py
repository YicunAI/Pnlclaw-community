"""Tests for PaperExecutionEngine — USDT-based derivatives simulation."""

from __future__ import annotations

import pytest
import pytest_asyncio

from pnlclaw_paper.paper_execution import PaperExecutionEngine
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
    async def test_place_market_order_with_leverage(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1000.0,
            leverage=10,
            margin_mode=MarginMode.CROSS,
            pos_side=PositionSide.LONG,
        )

        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 1000.0
        assert order.leverage == 10

    @pytest.mark.asyncio
    async def test_margin_deducted_from_balance(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10000.0,
            leverage=10,
        )

        balances = await engine.get_balances(ACCOUNT)
        # 100000 - 1000 (margin) - 5 (taker fee: 10000 * 0.0005) = 98995
        assert balances[0].free < 100_000.0
        assert balances[0].free == pytest.approx(98995.0)

    @pytest.mark.asyncio
    async def test_insufficient_margin_rejected(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        with pytest.raises(ValueError, match="Insufficient margin"):
            await engine.place_order(
                account_id=ACCOUNT,
                symbol="BTC-USDT-SWAP",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=2_000_000.0,
                leverage=1,
            )

    @pytest.mark.asyncio
    async def test_place_limit_order_pending(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1000.0,
            price=60000.0,
            leverage=10,
        )

        assert order.status in (OrderStatus.ACCEPTED, OrderStatus.CREATED)
        assert order.filled_quantity == 0.0

    @pytest.mark.asyncio
    async def test_limit_order_fills_on_price_tick(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1000.0,
            price=66000.0,
            leverage=10,
        )

        assert order.filled_quantity == 0.0

        await engine.on_price_tick("BTC-USDT-SWAP", 65000.0)

        orders = await engine.get_orders(ACCOUNT)
        filled = [o for o in orders if o.id == order.id]
        assert len(filled) == 1
        assert filled[0].status == OrderStatus.FILLED
        assert filled[0].filled_quantity == 1000.0

    @pytest.mark.asyncio
    async def test_cancel_order(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        order = await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1000.0,
            price=60000.0,
            leverage=10,
        )

        cancelled = await engine.cancel_order(order.id)
        assert cancelled.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_position_after_fill(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=5000.0,
            leverage=10,
            pos_side=PositionSide.LONG,
        )

        positions = await engine.get_positions(ACCOUNT)
        assert len(positions) >= 1
        btc_pos = next((p for p in positions if "BTC" in p.symbol), None)
        assert btc_pos is not None
        assert btc_pos.quantity == 5000.0
        assert btc_pos.side == OrderSide.BUY
        assert btc_pos.leverage == 10

    @pytest.mark.asyncio
    async def test_fills_tracked(self, engine: PaperExecutionEngine) -> None:
        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1000.0,
            leverage=10,
        )

        fills = await engine.get_fills(ACCOUNT)
        assert len(fills) >= 1
        assert fills[0].price == 67000.0
        assert fills[0].quantity == 1000.0

    @pytest.mark.asyncio
    async def test_fill_has_enriched_fields(self, engine: PaperExecutionEngine) -> None:
        """Fills contain side, pos_side, symbol, leverage, exec_type, fee_rate."""
        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1000.0,
            leverage=10,
            pos_side=PositionSide.LONG,
        )

        fills = await engine.get_fills(ACCOUNT)
        assert len(fills) >= 1
        f = fills[0]
        assert f.side == "buy"
        assert f.pos_side == "long"
        assert f.symbol == "BTC-USDT-SWAP"
        assert f.leverage == 10
        assert f.exec_type == "taker"
        assert f.fee_rate > 0

    @pytest.mark.asyncio
    async def test_account_total_realized_pnl_accumulates(self, engine: PaperExecutionEngine) -> None:
        """total_realized_pnl on account persists across position close/open cycles."""
        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=67000.0,
            leverage=10,
            pos_side=PositionSide.LONG,
        )

        await engine.on_price_tick("BTC-USDT-SWAP", 68000.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=67000.0,
            leverage=10,
            pos_side=PositionSide.LONG,
            reduce_only=True,
        )

        acct = engine._account_mgr.get_account(ACCOUNT)
        assert acct is not None
        assert acct.total_realized_pnl != 0.0

    @pytest.mark.asyncio
    async def test_account_total_fee_accumulates(self, engine: PaperExecutionEngine) -> None:
        """total_fee on account increases with each trade."""
        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10000.0,
            leverage=10,
        )

        acct = engine._account_mgr.get_account(ACCOUNT)
        assert acct is not None
        assert acct.total_fee > 0

    @pytest.mark.asyncio
    async def test_compute_equity(self, engine: PaperExecutionEngine) -> None:
        equity_before = engine.compute_equity(ACCOUNT)
        assert equity_before == pytest.approx(100_000.0)

        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)
        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10000.0,
            leverage=10,
            pos_side=PositionSide.LONG,
        )

        equity_after = engine.compute_equity(ACCOUNT)
        assert equity_after < 100_000.0

    @pytest.mark.asyncio
    async def test_update_fee_rates(self, engine: PaperExecutionEngine) -> None:
        engine.update_fee_rates(ACCOUNT, 0.0001, 0.0003)
        maker, taker = engine._get_fee_rates(ACCOUNT)
        assert maker == pytest.approx(0.0001)
        assert taker == pytest.approx(0.0003)

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

        await engine.on_price_tick("BTC-USDT-SWAP", 67000.0)

        await engine.place_order(
            account_id=ACCOUNT,
            symbol="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1000.0,
            leverage=10,
        )

        assert len(order_events) >= 1
        assert len(fill_events) >= 1
        assert len(position_events) >= 1
        assert len(balance_events) >= 1
