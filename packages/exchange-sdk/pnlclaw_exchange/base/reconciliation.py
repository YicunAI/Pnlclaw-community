"""REST reconciliation manager for WS-first execution tracking.

Provides periodic and on-demand REST-based state reconciliation to ensure
consistency between the exchange and local order/balance state. Used as a
fallback when:
- Private WebSocket reconnects (state may have changed during downtime)
- Gap detection (missed WS events)
- Periodic heartbeat (configurable interval, default 5 minutes)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from pnlclaw_exchange.trading import BalanceInfo, OrderResponse, TradingClient
from pnlclaw_types.trading import AccountSnapshot, BalanceUpdate, ExchangeOrderUpdate, OrderSide

logger = logging.getLogger(__name__)


class ReconciliationManager:
    """REST-based reconciliation for exchange state.

    This manager works alongside the private WS channels. WS is the primary
    data source; this manager provides the safety net.

    Usage::

        mgr = ReconciliationManager(
            trading_client=binance_adapter,
            on_snapshot=my_handler,
        )
        await mgr.start_periodic(interval_s=300)

        # On WS reconnect:
        snapshot = await mgr.reconcile_on_reconnect()

        await mgr.stop()
    """

    def __init__(
        self,
        trading_client: TradingClient,
        *,
        on_snapshot: Callable[[AccountSnapshot], Any] | None = None,
        on_orders: Callable[[list[OrderResponse]], Any] | None = None,
    ) -> None:
        self._client = trading_client
        self._on_snapshot = on_snapshot
        self._on_orders = on_orders
        self._periodic_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def exchange(self) -> str:
        return self._client.exchange_name

    async def reconcile_on_reconnect(self) -> AccountSnapshot:
        """Fetch full account state after a WS reconnect.

        Returns an AccountSnapshot with all non-zero balances.
        """
        logger.info("Reconciliation: fetching full state for %s", self.exchange)
        ts = int(time.time() * 1000)

        balances_raw = await self._client.get_balances()
        balances = [
            BalanceUpdate(
                exchange=self.exchange,
                asset=b.asset,
                free=b.free,
                locked=b.locked,
                timestamp=ts,
            )
            for b in balances_raw
        ]

        snapshot = AccountSnapshot(
            exchange=self.exchange,
            balances=balances,
            timestamp=ts,
        )

        if self._on_snapshot is not None:
            result = self._on_snapshot(snapshot)
            if asyncio.iscoroutine(result):
                await result

        logger.info(
            "Reconciliation complete: %d balances for %s",
            len(balances),
            self.exchange,
        )
        return snapshot

    async def reconcile_orders(
        self, symbol: str | None = None
    ) -> list[OrderResponse]:
        """Fetch all open orders from the exchange via REST.

        Args:
            symbol: Optional symbol filter.
        """
        logger.info("Reconciliation: fetching open orders for %s", self.exchange)
        orders = await self._client.get_open_orders(symbol)

        if self._on_orders is not None:
            result = self._on_orders(orders)
            if asyncio.iscoroutine(result):
                await result

        logger.info(
            "Order reconciliation: %d open orders for %s",
            len(orders),
            self.exchange,
        )
        return orders

    async def start_periodic(self, interval_s: float = 300.0) -> None:
        """Start periodic reconciliation at the given interval.

        Args:
            interval_s: Seconds between reconciliation runs (default 5 min).
        """
        if self._running:
            return
        self._running = True
        self._periodic_task = asyncio.create_task(
            self._periodic_loop(interval_s),
            name=f"reconciliation-{self.exchange}",
        )
        logger.info(
            "Periodic reconciliation started for %s (every %.0fs)",
            self.exchange,
            interval_s,
        )

    async def stop(self) -> None:
        """Stop periodic reconciliation."""
        self._running = False
        if self._periodic_task is not None and not self._periodic_task.done():
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
            self._periodic_task = None
        logger.info("Periodic reconciliation stopped for %s", self.exchange)

    async def _periodic_loop(self, interval_s: float) -> None:
        while self._running:
            try:
                await asyncio.sleep(interval_s)
                if not self._running:
                    break
                await self.reconcile_on_reconnect()
                await self.reconcile_orders()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in periodic reconciliation for %s", self.exchange)
