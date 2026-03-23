"""Overtrading protection guardrail.

Prevents excessive order placement: hourly/daily rate limits, frequent
reversal detection, and daily volume caps.
Source: distillation-plan-supplement-3 gap 20.
"""

from __future__ import annotations

import time
from collections import deque

from pydantic import BaseModel, Field

from pnlclaw_types import OrderSide, RiskLevel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class OvertradingConfig(BaseModel):
    """Configuration for overtrading detection."""

    max_orders_per_hour: int = Field(default=20, ge=1)
    max_orders_per_day: int = Field(default=100, ge=1)
    reversal_window_seconds: int = Field(
        default=300,
        ge=1,
        description="Window for detecting buy/sell reversals",
    )
    max_reversals_per_hour: int = Field(default=3, ge=1)


# ---------------------------------------------------------------------------
# Alert model
# ---------------------------------------------------------------------------


class OvertradingAlert(BaseModel):
    """Alert raised when overtrading is detected."""

    rule: str = Field(description="Rule that triggered: hourly_rate, daily_rate, frequent_reversal")
    current_value: float
    limit_value: float
    severity: RiskLevel
    message: str


# ---------------------------------------------------------------------------
# Internal order record
# ---------------------------------------------------------------------------


class _OrderRecord:
    """Lightweight record of a placed order for sliding-window checks."""

    __slots__ = ("timestamp", "symbol", "side")

    def __init__(self, timestamp: float, symbol: str, side: OrderSide) -> None:
        self.timestamp = timestamp
        self.symbol = symbol
        self.side = side


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class OvertradingDetector:
    """Detect and prevent excessive trading activity.

    Maintains a sliding window of recent orders and checks:
    - Hourly order rate limit
    - Daily order rate limit
    - Frequent reversal detection (buy→sell or sell→buy on same symbol)

    Args:
        config: Overtrading configuration. Uses defaults if not provided.
    """

    def __init__(self, config: OvertradingConfig | None = None) -> None:
        self._config = config or OvertradingConfig()
        self._orders: deque[_OrderRecord] = deque()

    def record_order(
        self,
        symbol: str,
        side: OrderSide,
        *,
        timestamp: float | None = None,
    ) -> None:
        """Record a placed order for rate tracking.

        Args:
            symbol: Trading pair symbol.
            side: Order side (BUY or SELL).
            timestamp: Order timestamp (defaults to current time).
        """
        ts = timestamp or time.time()
        self._orders.append(_OrderRecord(ts, symbol, side))
        # Prune entries older than 24 hours
        cutoff = ts - 86_400
        while self._orders and self._orders[0].timestamp < cutoff:
            self._orders.popleft()

    def check_hourly_rate(self, *, now: float | None = None) -> OvertradingAlert | None:
        """Check if the hourly order rate exceeds the limit."""
        current_time = now or time.time()
        cutoff = current_time - 3_600
        count = sum(1 for o in self._orders if o.timestamp >= cutoff)

        if count >= self._config.max_orders_per_hour:
            return OvertradingAlert(
                rule="hourly_rate",
                current_value=count,
                limit_value=self._config.max_orders_per_hour,
                severity=RiskLevel.RESTRICTED,
                message=(
                    f"Hourly order rate {count} "
                    f"exceeds limit {self._config.max_orders_per_hour}"
                ),
            )
        return None

    def check_daily_rate(self, *, now: float | None = None) -> OvertradingAlert | None:
        """Check if the daily order rate exceeds the limit."""
        current_time = now or time.time()
        cutoff = current_time - 86_400
        count = sum(1 for o in self._orders if o.timestamp >= cutoff)

        if count >= self._config.max_orders_per_day:
            return OvertradingAlert(
                rule="daily_rate",
                current_value=count,
                limit_value=self._config.max_orders_per_day,
                severity=RiskLevel.DANGEROUS,
                message=(
                    f"Daily order rate {count} "
                    f"exceeds limit {self._config.max_orders_per_day}"
                ),
            )
        return None

    def check_reversal(
        self,
        symbol: str,
        side: OrderSide,
        *,
        now: float | None = None,
    ) -> OvertradingAlert | None:
        """Check for frequent buy/sell reversals on the same symbol.

        A reversal is when the side flips (BUY→SELL or SELL→BUY) on the
        same symbol within the configured window.
        """
        current_time = now or time.time()
        window_start = current_time - self._config.reversal_window_seconds
        hour_start = current_time - 3_600

        # Count reversals in the last hour
        reversals = 0
        prev_side: OrderSide | None = None
        for order in self._orders:
            if order.symbol != symbol:
                continue
            if order.timestamp < hour_start:
                continue
            if prev_side is not None and order.side != prev_side:
                if order.timestamp >= window_start:
                    reversals += 1
            prev_side = order.side

        # Check if the new order creates another reversal
        if prev_side is not None and side != prev_side:
            reversals += 1

        if reversals >= self._config.max_reversals_per_hour:
            return OvertradingAlert(
                rule="frequent_reversal",
                current_value=reversals,
                limit_value=self._config.max_reversals_per_hour,
                severity=RiskLevel.RESTRICTED,
                message=(
                    f"{reversals} side reversals on {symbol} within "
                    f"the last hour (limit: {self._config.max_reversals_per_hour})"
                ),
            )
        return None

    def evaluate(
        self,
        symbol: str,
        side: OrderSide,
        *,
        now: float | None = None,
    ) -> list[OvertradingAlert]:
        """Run all overtrading checks. Returns list of triggered alerts."""
        alerts: list[OvertradingAlert] = []
        current_time = now or time.time()

        hourly = self.check_hourly_rate(now=current_time)
        if hourly:
            alerts.append(hourly)

        daily = self.check_daily_rate(now=current_time)
        if daily:
            alerts.append(daily)

        reversal = self.check_reversal(symbol, side, now=current_time)
        if reversal:
            alerts.append(reversal)

        return alerts

    def reset(self) -> None:
        """Clear all recorded orders."""
        self._orders.clear()
