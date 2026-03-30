"""Portfolio manager for backtesting.

Tracks cash balance, open positions, and the equity curve over time.
"""

from __future__ import annotations

from pnlclaw_types.trading import Fill, OrderSide


class Portfolio:
    """In-memory portfolio that tracks cash, positions, and equity.

    Args:
        initial_cash: Starting cash balance in quote currency.
    """

    def __init__(self, initial_cash: float = 10_000.0) -> None:
        self._initial_cash = initial_cash
        self._cash = initial_cash
        # symbol -> quantity held (positive = long)
        self._positions: dict[str, float] = {}
        # symbol -> last known price (for mark-to-market)
        self._last_prices: dict[str, float] = {}
        # equity snapshot after each kline update
        self._equity_curve: list[float] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cash(self) -> float:
        """Current cash balance."""
        return self._cash

    @property
    def positions(self) -> dict[str, float]:
        """Current positions (symbol -> quantity)."""
        return dict(self._positions)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def get_position_quantity(self, symbol: str) -> float:
        """Return the quantity held for *symbol* (0 if no position)."""
        return self._positions.get(symbol, 0.0)

    def apply_fill(self, fill: Fill, side: OrderSide) -> None:
        """Apply a fill to update cash and position.

        Args:
            fill: The execution fill.
            side: Direction of the original order.
        """
        cost = fill.price * fill.quantity
        symbol = fill.symbol if fill.symbol else "BTC/USDT"

        if side == OrderSide.BUY:
            self._cash -= cost + fill.fee
            self._positions[symbol] = self._positions.get(symbol, 0.0) + fill.quantity
        else:
            self._cash += cost - fill.fee
            self._positions[symbol] = self._positions.get(symbol, 0.0) - fill.quantity
            # Clamp near-zero to zero to avoid floating-point dust
            if abs(self._positions[symbol]) < 1e-12:
                self._positions[symbol] = 0.0

    def update_equity(self, symbol: str, current_price: float) -> None:
        """Recalculate portfolio equity after a bar closes.

        Args:
            symbol: The symbol whose price just updated.
            current_price: The closing price of the bar.
        """
        self._last_prices[symbol] = current_price
        equity = self._cash
        for sym, qty in self._positions.items():
            price = self._last_prices.get(sym, 0.0)
            equity += qty * price
        self._equity_curve.append(equity)

    def get_equity_curve(self) -> list[float]:
        """Return the full equity curve as a list of floats."""
        return list(self._equity_curve)

    def reset(self) -> None:
        """Reset portfolio to initial state."""
        self._cash = self._initial_cash
        self._positions.clear()
        self._last_prices.clear()
        self._equity_curve.clear()
