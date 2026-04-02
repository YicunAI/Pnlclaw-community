"""ExecutionEngine protocol — unified interface for Paper and Live execution.

Both PaperExecutionEngine and LiveExecutionEngine implement this protocol,
making the API layer and frontend completely agnostic of the execution mode.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

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


@runtime_checkable
class ExecutionEngine(Protocol):
    """Unified execution engine interface for Paper and Live modes.

    All state queries and mutations go through this interface, allowing
    seamless mode switching from the API layer.
    """

    @property
    def mode(self) -> ExecutionMode:
        """Return the current execution mode (paper or live)."""
        ...

    @property
    def exchange(self) -> str:
        """Return the exchange identifier (e.g. 'binance', 'paper')."""
        ...

    async def start(self) -> None:
        """Start the engine (connect WS, initialize state, etc.)."""
        ...

    async def stop(self) -> None:
        """Stop the engine and clean up resources."""
        ...

    # ------------------------------------------------------------------
    # Order operations
    # ------------------------------------------------------------------

    async def place_order(
        self,
        *,
        account_id: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: float | None = None,
        stop_price: float | None = None,
    ) -> Order:
        """Place a new order.

        Args:
            account_id: Trading account identifier.
            symbol: Normalized trading pair (e.g. 'BTC/USDT').
            side: Buy or sell.
            order_type: Market, limit, stop_market, or stop_limit.
            quantity: Order size in base currency.
            price: Limit price (required for limit/stop_limit).
            stop_price: Stop trigger price (required for stop types).

        Returns:
            The created Order with initial status.
        """
        ...

    async def cancel_order(self, order_id: str) -> Order:
        """Cancel an open order.

        Args:
            order_id: Internal or exchange order ID.

        Returns:
            The updated Order with cancelled status.
        """
        ...

    async def get_orders(self, account_id: str, *, status: OrderStatus | None = None) -> list[Order]:
        """Get orders for an account, optionally filtered by status."""
        ...

    async def get_open_orders(self, account_id: str) -> list[Order]:
        """Get all open (non-terminal) orders for an account."""
        ...

    # ------------------------------------------------------------------
    # Position queries
    # ------------------------------------------------------------------

    async def get_positions(self, account_id: str) -> list[Position]:
        """Get all open positions for an account."""
        ...

    # ------------------------------------------------------------------
    # Balance queries
    # ------------------------------------------------------------------

    async def get_balances(self, account_id: str) -> list[BalanceUpdate]:
        """Get current balances for an account."""
        ...

    # ------------------------------------------------------------------
    # Trade history
    # ------------------------------------------------------------------

    async def get_fills(self, account_id: str) -> list[Fill]:
        """Get all fills (trade executions) for an account."""
        ...

    # ------------------------------------------------------------------
    # Event callbacks
    # ------------------------------------------------------------------

    def on_order_update(self, callback: Callable[[Order], Any]) -> None:
        """Register a callback for order state changes."""
        ...

    def on_fill(self, callback: Callable[[Fill], Any]) -> None:
        """Register a callback for new fills."""
        ...

    def on_position_update(self, callback: Callable[[Position], Any]) -> None:
        """Register a callback for position changes."""
        ...

    def on_balance_update(self, callback: Callable[[list[BalanceUpdate]], Any]) -> None:
        """Register a callback for balance changes."""
        ...

    def on_position_update_scoped(self, callback: Callable[[str, Position], Any]) -> None:
        """Register a callback receiving (account_id, position) for per-account routing."""
        ...

    def on_balance_update_scoped(self, callback: Callable[[str, list[BalanceUpdate]], Any]) -> None:
        """Register a callback receiving (account_id, balances) for per-account routing."""
        ...
