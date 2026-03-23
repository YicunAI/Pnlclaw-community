"""Tests for ReconciliationManager."""

from __future__ import annotations

import asyncio

import pytest

from pnlclaw_exchange.base.reconciliation import ReconciliationManager
from pnlclaw_exchange.trading import BalanceInfo, OrderResponse, TradingClient
from pnlclaw_types.trading import AccountSnapshot, OrderSide, OrderStatus, OrderType


class MockTradingClient(TradingClient):
    """Minimal TradingClient for testing reconciliation."""

    @property
    def exchange_name(self) -> str:
        return "mock"

    async def place_order(self, request):  # type: ignore[override]
        raise NotImplementedError

    async def cancel_order(self, *, symbol: str, order_id: str):  # type: ignore[override]
        raise NotImplementedError

    async def get_order(self, *, symbol: str, order_id: str):  # type: ignore[override]
        raise NotImplementedError

    async def get_open_orders(self, symbol=None):  # type: ignore[override]
        return [
            OrderResponse(
                exchange="mock",
                order_id="ord-1",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                status=OrderStatus.ACCEPTED,
                quantity=0.01,
                price=60000.0,
            )
        ]

    async def get_balances(self):  # type: ignore[override]
        return [
            BalanceInfo(asset="BTC", free=0.5, locked=0.1, total=0.6),
            BalanceInfo(asset="USDT", free=10000.0, locked=500.0, total=10500.0),
        ]

    async def test_connectivity(self) -> bool:
        return True


@pytest.fixture
def mock_client() -> MockTradingClient:
    return MockTradingClient()


class TestReconciliationManager:
    @pytest.mark.asyncio
    async def test_reconcile_on_reconnect(self, mock_client: MockTradingClient) -> None:
        snapshots: list[AccountSnapshot] = []

        async def on_snap(snap: AccountSnapshot) -> None:
            snapshots.append(snap)

        mgr = ReconciliationManager(mock_client, on_snapshot=on_snap)
        snapshot = await mgr.reconcile_on_reconnect()

        assert snapshot.exchange == "mock"
        assert len(snapshot.balances) == 2
        assert snapshot.balances[0].asset == "BTC"
        assert snapshot.balances[0].free == 0.5
        assert len(snapshots) == 1

    @pytest.mark.asyncio
    async def test_reconcile_orders(self, mock_client: MockTradingClient) -> None:
        received: list[list[OrderResponse]] = []

        async def on_orders(orders: list[OrderResponse]) -> None:
            received.append(orders)

        mgr = ReconciliationManager(mock_client, on_orders=on_orders)
        orders = await mgr.reconcile_orders()

        assert len(orders) == 1
        assert orders[0].order_id == "ord-1"
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_start_stop_periodic(self, mock_client: MockTradingClient) -> None:
        mgr = ReconciliationManager(mock_client)
        await mgr.start_periodic(interval_s=0.1)
        await asyncio.sleep(0.05)
        await mgr.stop()
