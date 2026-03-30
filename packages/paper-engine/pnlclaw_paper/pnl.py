"""PnL calculation for paper trading.

Computes realized PnL (from closed portions), unrealized PnL
(mark-to-market), and total PnL with fee deductions.
"""

from __future__ import annotations

import time

from pnlclaw_types.trading import OrderSide, PnLRecord, Position


def calculate_pnl(
    position: Position,
    current_price: float,
    *,
    total_fees: float = 0.0,
) -> PnLRecord:
    """Calculate PnL for a position at the current market price.

    Args:
        position: The position to evaluate.
        current_price: Current market price for unrealized PnL.
        total_fees: Accumulated fees for this symbol.

    Returns:
        PnLRecord with realized, unrealized, total, and fees.
    """
    realized = position.realized_pnl

    # Unrealized PnL: use base quantity for price-based calculation
    base_qty = getattr(position, "quantity_base", 0.0) or (
        position.quantity / position.avg_entry_price
        if position.avg_entry_price > 0
        else 0.0
    )
    if base_qty > 0 and current_price > 0:
        if position.side == OrderSide.BUY:
            unrealized = (current_price - position.avg_entry_price) * base_qty
        else:
            unrealized = (position.avg_entry_price - current_price) * base_qty
    else:
        unrealized = 0.0

    total = realized + unrealized - total_fees

    return PnLRecord(
        symbol=position.symbol,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_pnl=total,
        fees=total_fees,
        timestamp=int(time.time() * 1000),
    )


def calculate_account_pnl(
    positions: list[Position],
    prices: dict[str, float],
    fees_by_symbol: dict[str, float] | None = None,
) -> list[PnLRecord]:
    """Calculate PnL for all positions in an account.

    Args:
        positions: List of positions.
        prices: symbol → current price mapping.
        fees_by_symbol: symbol → total fees mapping.

    Returns:
        List of PnLRecord, one per position.
    """
    fees = fees_by_symbol or {}
    records: list[PnLRecord] = []
    for pos in positions:
        price = prices.get(pos.symbol, 0.0)
        symbol_fees = fees.get(pos.symbol, 0.0)
        records.append(calculate_pnl(pos, price, total_fees=symbol_fees))
    return records
