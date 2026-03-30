"""Paper trading position management with derivatives support.

Handles long/short positions with leverage, margin calculation,
liquidation price estimation, and USDT-denominated position sizing.
Mirrors OKX USDT-margined perpetual swap behavior.
"""

from __future__ import annotations

import time
from typing import Any

from pnlclaw_types.common import Symbol
from pnlclaw_types.trading import Fill, MarginMode, OrderSide, Position, PositionSide


def _estimate_liquidation_price(
    entry_price: float,
    leverage: int,
    side: OrderSide,
    margin_mode: MarginMode,
    available_balance: float | None = None,
    position_usdt: float | None = None,
) -> float | None:
    """Estimate liquidation price using OKX's official USDT-margined formula.

    **Isolated margin** (from OKX docs "Calculation of contract's profit and loss"):

      Long:  liqPx = (margin_balance - contracts * entry_price)
                     / [contracts * (mmr + fee_rate - 1)]
      Short: liqPx = (margin_balance + contracts * entry_price)
                     / [contracts * (mmr + fee_rate + 1)]

      where margin_balance = position_usdt / leverage  (initial margin)
            contracts       = position_usdt / entry_price  (base qty)
            mmr             = maintenance margin ratio (0.4% default)
            fee_rate        = taker fee rate for liquidation (0.05%)

    **Cross margin**: same formula but margin_balance = full account balance.
    """
    if leverage <= 1:
        return None
    if entry_price <= 0:
        return None

    MMR = 0.004
    FEE_RATE = 0.0005

    pos_usdt = position_usdt if position_usdt and position_usdt > 0 else entry_price
    contracts = pos_usdt / entry_price

    if contracts <= 0:
        return None

    if margin_mode == MarginMode.ISOLATED:
        margin_balance = pos_usdt / leverage
    else:
        if available_balance is not None and available_balance > 0:
            margin_balance = available_balance
        else:
            margin_balance = pos_usdt / leverage

    if side == OrderSide.BUY:
        denominator = contracts * (MMR + FEE_RATE - 1)
        if denominator == 0:
            return None
        liq = (margin_balance - contracts * entry_price) / denominator
    else:
        denominator = contracts * (MMR + FEE_RATE + 1)
        if denominator == 0:
            return None
        liq = (margin_balance + contracts * entry_price) / denominator

    return max(liq, 0.0) if liq is not None else None


class PositionManager:
    """Manages open positions for paper trading accounts.

    Positions are keyed by (account_id, symbol, pos_side) to support
    dual-position mode (simultaneous long and short).
    """

    def __init__(self) -> None:
        self._positions: dict[tuple[str, str, str], Position] = {}

    def apply_fill(self, account_id: str, fill: Fill, side: OrderSide) -> Position:
        raise NotImplementedError("Use apply_fill_with_symbol instead")

    def apply_fill_with_symbol(
        self,
        account_id: str,
        symbol: Symbol,
        fill: Fill,
        side: OrderSide,
        leverage: int = 1,
        margin_mode: MarginMode = MarginMode.CROSS,
        pos_side: PositionSide = PositionSide.NET,
        available_balance: float | None = None,
    ) -> tuple[Position, float]:
        """Apply a fill to update or create a position.

        ``fill.quantity`` is the USDT notional of this fill.
        ``fill.price`` is the execution price per unit of base currency.
        ``available_balance`` is the account's current balance, used for
        cross-margin liquidation price estimation.
        """
        key = (account_id, symbol, pos_side.value)
        now_ms = int(time.time() * 1000)
        existing = self._positions.get(key)

        fill_usdt = fill.quantity
        fill_base = fill_usdt / fill.price if fill.price > 0 else 0.0

        if existing is None or existing.quantity == 0:
            margin = fill_usdt / leverage
            liq = _estimate_liquidation_price(
                fill.price, leverage, side, margin_mode,
                available_balance=available_balance,
                position_usdt=fill_usdt,
            )
            pos = Position(
                symbol=symbol,
                side=side,
                pos_side=pos_side,
                quantity=fill_usdt,
                quantity_base=fill_base,
                avg_entry_price=fill.price,
                leverage=leverage,
                margin_mode=margin_mode,
                margin=margin,
                liquidation_price=liq,
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0,
                realized_pnl=0.0,
                current_price=fill.price,
                opened_at=fill.timestamp,
                updated_at=now_ms,
            )
            self._positions[key] = pos
            return pos, 0.0

        if existing.side == side:
            realized = 0.0
            new_qty = existing.quantity + fill_usdt
            new_base = existing.quantity_base + fill_base
            new_avg = (
                existing.avg_entry_price * existing.quantity_base + fill.price * fill_base
            ) / new_base if new_base > 0 else fill.price
            existing.quantity = new_qty
            existing.quantity_base = new_base
            existing.avg_entry_price = new_avg
            existing.margin = new_qty / existing.leverage
            existing.liquidation_price = _estimate_liquidation_price(
                new_avg, existing.leverage, side, existing.margin_mode,
                available_balance=available_balance,
                position_usdt=new_qty,
            )
            existing.updated_at = now_ms
            return existing, realized
        else:
            close_usdt = min(fill_usdt, existing.quantity)
            close_base = close_usdt / existing.avg_entry_price if existing.avg_entry_price > 0 else 0
            remaining_usdt = fill_usdt - close_usdt

            if existing.side == OrderSide.BUY:
                realized = (fill.price - existing.avg_entry_price) * close_base
            else:
                realized = (existing.avg_entry_price - fill.price) * close_base

            existing.realized_pnl += realized
            existing.quantity -= close_usdt
            existing.quantity_base = existing.quantity / existing.avg_entry_price if existing.avg_entry_price > 0 else 0
            existing.margin = existing.quantity / existing.leverage if existing.quantity > 0 else 0
            existing.updated_at = now_ms

            if existing.quantity <= 0 and remaining_usdt > 0:
                remaining_base = remaining_usdt / fill.price if fill.price > 0 else 0
                existing.side = side
                existing.quantity = remaining_usdt
                existing.quantity_base = remaining_base
                existing.avg_entry_price = fill.price
                existing.margin = remaining_usdt / leverage
                existing.liquidation_price = _estimate_liquidation_price(
                    fill.price, leverage, side, margin_mode
                )
            elif existing.quantity <= 0:
                existing.quantity = 0
                existing.quantity_base = 0
                existing.margin = 0
                existing.liquidation_price = None

            return existing, realized

    def get_position(self, account_id: str, symbol: Symbol) -> Position | None:
        for key, pos in self._positions.items():
            if key[0] == account_id and key[1] == symbol:
                return pos
        return None

    def get_positions(self, account_id: str) -> list[Position]:
        return [pos for (aid, _, _), pos in self._positions.items() if aid == account_id]

    def get_open_positions(self, account_id: str) -> list[Position]:
        return [p for p in self.get_positions(account_id) if p.quantity > 0]

    def update_unrealized_pnl(
        self,
        account_id: str,
        symbol: Symbol,
        current_price: float,
    ) -> list[Position]:
        """Recalculate unrealized PnL for all positions of a symbol."""
        updated = []
        for key, pos in self._positions.items():
            if key[0] != account_id or key[1] != symbol or pos.quantity == 0:
                continue
            pos.current_price = current_price
            if pos.side == OrderSide.BUY:
                pos.unrealized_pnl = (current_price - pos.avg_entry_price) * pos.quantity_base
            else:
                pos.unrealized_pnl = (pos.avg_entry_price - current_price) * pos.quantity_base
            if pos.margin > 0:
                pos.unrealized_pnl_pct = (pos.unrealized_pnl / pos.margin) * 100
            pos.updated_at = int(time.time() * 1000)
            updated.append(pos)
        return updated

    def clear_positions(self, account_id: str) -> None:
        """Remove all positions for an account."""
        keys_to_delete = [
            k for k in self._positions.keys() if k[0] == account_id
        ]
        for k in keys_to_delete:
            del self._positions[k]

    # -- serialization ---------------------------------------------------------

    def get_all_data(self) -> dict[str, Any]:
        return {
            f"{aid}:{sym}:{ps}": pos.model_dump()
            for (aid, sym, ps), pos in self._positions.items()
        }

    def load_data(self, data: dict[str, Any]) -> None:
        self._positions = {}
        for key_str, pos_data in data.items():
            parts = key_str.split(":", 2)
            if len(parts) == 3:
                self._positions[(parts[0], parts[1], parts[2])] = Position.model_validate(pos_data)
            elif len(parts) == 2:
                self._positions[(parts[0], parts[1], "net")] = Position.model_validate(pos_data)
