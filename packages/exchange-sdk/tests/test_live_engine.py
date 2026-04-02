"""Tests for LiveExecutionEngine."""

from __future__ import annotations

import pytest
import pytest_asyncio

from pnlclaw_exchange.execution.live_engine import LiveExecutionEngine
from pnlclaw_exchange.trading import BalanceInfo, OrderRequest, OrderResponse, TradingClient
from pnlclaw_types.trading import (
    BalanceUpdate,
    ExchangeOrderUpdate,
    ExecutionMode,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)


class MockLiveTradingClient(TradingClient):
    """Mock client for testing LiveExecutionEngine."""

    def __init__(self) -> None:
        self.placed: list[OrderRequest] = []
        self.cancelled: list[tuple[str, str]] = []

    @property
    def exchange_name(self) -> str:
        return "mock-live"

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        self.placed.append(request)
        return OrderResponse(
            exchange="mock-live",
            order_id=f"exch-{len(self.placed)}",
            client_order_id=request.client_order_id or "",
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            status=OrderStatus.ACCEPTED,
            quantity=request.quantity,
            price=request.price,
        )

    async def cancel_order(self, *, symbol: str, order_id: str) -> OrderResponse:
        self.cancelled.append((symbol, order_id))
        return OrderResponse(
            exchange="mock-live",
            order_id=order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            status=OrderStatus.CANCELLED,
            quantity=0,
        )

    async def get_order(self, *, symbol: str, order_id: str) -> OrderResponse:
        return OrderResponse(
            exchange="mock-live",
            order_id=order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            status=OrderStatus.ACCEPTED,
            quantity=0,
        )

    async def get_open_orders(self, symbol=None) -> list[OrderResponse]:  # type: ignore[override]
        return []

    async def get_balances(self) -> list[BalanceInfo]:
        return [BalanceInfo(asset="USDT", free=50000.0, locked=0.0, total=50000.0)]

    async def test_connectivity(self) -> bool:
        return True


@pytest_asyncio.fixture
async def engine() -> LiveExecutionEngine:
    client = MockLiveTradingClient()
    eng = LiveExecutionEngine(client, reconciliation_interval_s=9999)
    await eng.start()
    return eng


class TestLiveExecutionEngine:
    @pytest.mark.asyncio
    async def test_mode(self, engine: LiveExecutionEngine) -> None:
        assert engine.mode == ExecutionMode.LIVE

    @pytest.mark.asyncio
    async def test_place_order(self, engine: LiveExecutionEngine) -> None:
        order_events: list[Order] = []
        engine.on_order_update(lambda o: order_events.append(o))

        order = await engine.place_order(
            account_id="test",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=60000.0,
        )

        assert order.symbol == "BTC/USDT"
        assert order.status == OrderStatus.ACCEPTED
        assert len(order_events) >= 1

    @pytest.mark.asyncio
    async def test_cancel_order(self, engine: LiveExecutionEngine) -> None:
        order = await engine.place_order(
            account_id="test",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=60000.0,
        )

        cancelled = await engine.cancel_order(order.id)
        assert cancelled.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_handle_exchange_order_update(self, engine: LiveExecutionEngine) -> None:
        fill_events: list[Fill] = []
        engine.on_fill(lambda f: fill_events.append(f))

        await engine.place_order(
            account_id="test",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=60000.0,
        )

        # Simulate exchange WS pushing a fill
        update = ExchangeOrderUpdate(
            exchange="mock-live",
            exchange_order_id="exch-1",
            client_order_id=None,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="LIMIT",
            status="FILLED",
            quantity=0.01,
            filled_quantity=0.01,
            avg_fill_price=60000.0,
            last_fill_price=60000.0,
            last_fill_quantity=0.01,
            commission=0.006,
            commission_asset="USDT",
            timestamp=1711000000000,
        )

        await engine.handle_exchange_order_update(update)

        orders = await engine.get_orders("test")
        filled = [o for o in orders if o.status == OrderStatus.FILLED]
        assert len(filled) >= 1
        assert len(fill_events) >= 1

    @pytest.mark.asyncio
    async def test_handle_balance_update(self, engine: LiveExecutionEngine) -> None:
        balance_events: list[list[BalanceUpdate]] = []
        engine.on_balance_update(lambda b: balance_events.append(b))

        updates = [
            BalanceUpdate(
                exchange="mock-live",
                asset="USDT",
                free=99000.0,
                locked=1000.0,
                timestamp=1711000000000,
            )
        ]

        await engine.handle_balance_update(updates)

        balances = await engine.get_balances("test")
        assert len(balances) >= 1
        assert balances[0].free == 99000.0
        assert len(balance_events) >= 1

    @pytest.mark.asyncio
    async def test_get_fills(self, engine: LiveExecutionEngine) -> None:
        fills = await engine.get_fills("test")
        assert isinstance(fills, list)

    @pytest.mark.asyncio
    async def test_stop(self, engine: LiveExecutionEngine) -> None:
        await engine.stop()
