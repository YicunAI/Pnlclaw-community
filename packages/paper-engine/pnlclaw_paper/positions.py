"""Paper trading position management.

Handles long/short positions, partial closes, and weighted average entry
price calculation.
"""

from __future__ import annotations

import time
from typing import Any

from pnlclaw_types.common import Symbol
from pnlclaw_types.trading import Fill, OrderSide, Position


class PositionManager:
    """Manages open positions for paper trading accounts.

    Positions are keyed by (account_id, symbol).
    """

    def __init__(self) -> None:
        # (account_id, symbol) → Position
        self._positions: dict[tuple[str, str], Position] = {}

    def apply_fill(self, account_id: str, fill: Fill, side: OrderSide) -> Position:
        """Apply a fill to update or create a position.

        Logic:
          - If no existing position: create new position.
          - If same direction: increase position, recalculate avg entry.
          - If opposite direction: reduce/close position, realize PnL.

        Args:
            account_id: The paper account ID.
            fill: The fill to apply.
            side: The order side that generated this fill.

        Returns:
            Updated Position.
        """
        # We need to know the symbol from the fill's parent order
        # The caller must provide this context. For simplicity, we'll
        # look up by order_id or require symbol on the fill.
        # Since Fill doesn't carry symbol, we need the caller to provide it.
        # We'll use a separate method signature.
        raise NotImplementedError("Use apply_fill_with_symbol instead")

    def apply_fill_with_symbol(
        self,
        account_id: str,
        symbol: Symbol,
        fill: Fill,
        side: OrderSide,
    ) -> tuple[Position, float]:
        """Apply a fill to update or create a position.

        Args:
            account_id: The paper account ID.
            symbol: Trading pair.
            fill: The fill to apply.
            side: The order side.

        Returns:
            Tuple of (updated Position, realized PnL from this fill).
        """
        key = (account_id, symbol)
        now_ms = int(time.time() * 1000)
        existing = self._positions.get(key)

        if existing is None or existing.quantity == 0:
            # New position
            pos = Position(
                symbol=symbol,
                side=side,
                quantity=fill.quantity,
                avg_entry_price=fill.price,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                opened_at=fill.timestamp,
                updated_at=now_ms,
            )
            self._positions[key] = pos
            return pos, 0.0

        # Existing position
        if existing.side == side:
            # Same direction — increase position
            realized = 0.0
            new_qty = existing.quantity + fill.quantity
            new_avg = (
                existing.avg_entry_price * existing.quantity + fill.price * fill.quantity
            ) / new_qty
            existing.quantity = new_qty
            existing.avg_entry_price = new_avg
            existing.updated_at = now_ms
            return existing, realized
        else:
            # Opposite direction — reduce/close position
            close_qty = min(fill.quantity, existing.quantity)
            remaining_fill = fill.quantity - close_qty

            # Calculate realized PnL for the closed portion
            if existing.side == OrderSide.BUY:
                # Long position closed by sell
                realized = (fill.price - existing.avg_entry_price) * close_qty
            else:
                # Short position closed by buy
                realized = (existing.avg_entry_price - fill.price) * close_qty

            existing.realized_pnl += realized
            existing.quantity -= close_qty
            existing.updated_at = now_ms

            if existing.quantity == 0 and remaining_fill > 0:
                # Flip position direction
                existing.side = side
                existing.quantity = remaining_fill
                existing.avg_entry_price = fill.price
            elif existing.quantity == 0:
                # Position fully closed — keep it with 0 quantity
                pass

            return existing, realized

    def get_position(self, account_id: str, symbol: Symbol) -> Position | None:
        """Get position for a specific account and symbol."""
        return self._positions.get((account_id, symbol))

    def get_positions(self, account_id: str) -> list[Position]:
        """Get all positions for an account."""
        return [pos for (aid, _), pos in self._positions.items() if aid == account_id]

    def get_open_positions(self, account_id: str) -> list[Position]:
        """Get positions with quantity > 0."""
        return [p for p in self.get_positions(account_id) if p.quantity > 0]

    def update_unrealized_pnl(
        self,
        account_id: str,
        symbol: Symbol,
        current_price: float,
    ) -> Position | None:
        """Recalculate unrealized PnL for a position at current price."""
        pos = self._positions.get((account_id, symbol))
        if pos is None or pos.quantity == 0:
            return pos

        if pos.side == OrderSide.BUY:
            pos.unrealized_pnl = (current_price - pos.avg_entry_price) * pos.quantity
        else:
            pos.unrealized_pnl = (pos.avg_entry_price - current_price) * pos.quantity

        pos.updated_at = int(time.time() * 1000)
        return pos

    # -- serialization ---------------------------------------------------------

    def get_all_data(self) -> dict[str, Any]:
        """Return internal state for serialization."""
        return {f"{aid}:{sym}": pos.model_dump() for (aid, sym), pos in self._positions.items()}

    def load_data(self, data: dict[str, Any]) -> None:
        """Load state from deserialized data."""
        self._positions = {}
        for key_str, pos_data in data.items():
            parts = key_str.split(":", 1)
            if len(parts) == 2:
                self._positions[(parts[0], parts[1])] = Position.model_validate(pos_data)
