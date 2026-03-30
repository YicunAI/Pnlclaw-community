"""Strategy runtime — receives KlineEvent stream, evaluates rules, emits Signals."""

from __future__ import annotations

import time
from typing import cast

import pandas as pd

from pnlclaw_strategy.compiler import CompiledCondition, CompiledStrategy
from pnlclaw_strategy.models import RiskParams
from pnlclaw_types.market import KlineEvent
from pnlclaw_types.strategy import Signal, StrategyDirection
from pnlclaw_types.trading import OrderSide


class StrategyRuntime:
    """Runtime that processes kline events through a compiled strategy.

    Maintains an internal DataFrame of historical prices, computes
    indicator values, and evaluates entry/exit conditions to produce
    trading Signals.

    Args:
        compiled: A CompiledStrategy from the compiler.
        max_bars: Maximum number of bars to retain in the internal DataFrame.
    """

    def __init__(
        self,
        compiled: CompiledStrategy,
        max_bars: int = 500,
        risk_params: RiskParams | None = None,
        direction: StrategyDirection = StrategyDirection.LONG_ONLY,
    ) -> None:
        self._compiled = compiled
        self._max_bars = max_bars
        self._bars: list[dict] = []
        self._position: str = "flat"  # "flat", "long", "short"
        self._risk_params = risk_params or compiled.config.parsed_risk_params
        self._entry_price: float = 0.0
        self._direction = direction

    @property
    def config(self) -> CompiledStrategy:
        """The compiled strategy driving this runtime."""
        return self._compiled

    @property
    def position(self) -> str:
        """Current position state: 'flat', 'long', or 'short'."""
        return self._position

    @property
    def bar_count(self) -> int:
        """Number of bars in the internal DataFrame."""
        return len(self._bars)

    def on_kline(self, event: KlineEvent) -> Signal | None:
        """Process a kline event and optionally emit a Signal.

        Only processes closed (finalized) klines to avoid premature signals.

        Args:
            event: A KlineEvent from the market data stream.

        Returns:
            A Signal if entry/exit conditions are met, None otherwise.
        """
        if not event.closed:
            return None

        # Append bar data
        self._bars.append(
            {
                "timestamp": event.timestamp,
                "open": event.open,
                "high": event.high,
                "low": event.low,
                "close": event.close,
                "volume": event.volume,
            }
        )

        # Trim to max_bars
        if len(self._bars) > self._max_bars:
            self._bars = self._bars[-self._max_bars :]

        # Need at least some bars to evaluate
        if len(self._bars) < 2:
            return None

        # P7: Risk controls are price-based and don't need indicators
        if self._position in ("long", "short"):
            risk_signal = self._check_risk(event, self._position)
            if risk_signal is not None:
                return risk_signal

        df = pd.DataFrame(self._bars)

        # Compute all indicator columns
        for col_name, indicator in self._compiled.indicators.items():
            if col_name in df.columns:
                continue  # already computed (e.g. MACD sub-columns)
            if hasattr(indicator, "calculate_full") and "macd" in col_name:
                # MACD family — compute all three columns at once
                result = indicator.calculate_full(df)
                base = col_name
                signal_col = base.replace("macd", "macd_signal", 1)
                hist_col = base.replace("macd", "macd_histogram", 1)
                df[base] = result.macd_line
                df[signal_col] = result.signal_line
                df[hist_col] = result.histogram
            elif hasattr(indicator, "calculate_full") and "bbands" in col_name:
                # Bollinger Bands family
                result = indicator.calculate_full(df)
                base = col_name
                upper_col = base.replace("bbands", "bbands_upper", 1)
                middle_col = base.replace("bbands", "bbands_middle", 1)
                lower_col = base.replace("bbands", "bbands_lower", 1)
                df[base] = result.middle
                df[upper_col] = result.upper
                df[middle_col] = result.middle
                df[lower_col] = result.lower
            else:
                df[col_name] = indicator.calculate(df)

        # Check if we have enough data (last row must have all indicators computed)
        last_idx = len(df) - 1
        for col_name in self._compiled.indicators:
            if pd.isna(df[col_name].iloc[last_idx]):
                return None  # Not enough data yet

        # FX06: Evaluate conditions filtered by strategy direction
        signal = None
        allow_long = self._direction in (StrategyDirection.LONG_ONLY, StrategyDirection.NEUTRAL)
        allow_short = self._direction in (StrategyDirection.SHORT_ONLY, StrategyDirection.NEUTRAL)

        if self._position == "flat":
            if allow_long and self._compiled.long_entry_conditions and self._all_conditions_met(
                df, self._compiled.long_entry_conditions
            ):
                signal = self._make_signal(event, OrderSide.BUY, "Long entry conditions met")
                self._position = "long"
                self._entry_price = event.close

            elif allow_short and self._compiled.short_entry_conditions and self._all_conditions_met(
                df, self._compiled.short_entry_conditions
            ):
                signal = self._make_signal(event, OrderSide.SELL, "Short entry conditions met")
                self._position = "short"
                self._entry_price = event.close

        elif self._position == "long":
            if self._compiled.close_long_conditions and self._all_conditions_met(
                df, self._compiled.close_long_conditions
            ):
                signal = self._make_signal(event, OrderSide.SELL, "Close long conditions met")
                self._position = "flat"

        elif self._position == "short":
            if self._compiled.close_short_conditions and self._all_conditions_met(
                df, self._compiled.close_short_conditions
            ):
                signal = self._make_signal(event, OrderSide.BUY, "Close short conditions met")
                self._position = "flat"

        return signal

    def _all_conditions_met(self, df: pd.DataFrame, conditions: list[CompiledCondition]) -> bool:
        """Check if ALL conditions in the list are currently met."""
        for cond in conditions:
            if not self._evaluate_condition(df, cond):
                return False
        return True

    def _check_risk(self, event: KlineEvent, direction: str) -> Signal | None:
        """Check stop-loss and take-profit risk limits.

        Returns a closing Signal if a risk threshold is breached, None otherwise.
        """
        if self._entry_price <= 0:
            return None
        rp = self._risk_params
        if rp is None:
            return None

        current = event.close
        if direction == "long":
            pnl_pct = (current - self._entry_price) / self._entry_price
            if rp.stop_loss_pct is not None and pnl_pct <= -rp.stop_loss_pct:
                self._position = "flat"
                return self._make_signal(event, OrderSide.SELL, f"Stop loss triggered ({pnl_pct:.2%})")
            if rp.take_profit_pct is not None and pnl_pct >= rp.take_profit_pct:
                self._position = "flat"
                return self._make_signal(event, OrderSide.SELL, f"Take profit triggered ({pnl_pct:.2%})")
        elif direction == "short":
            pnl_pct = (self._entry_price - current) / self._entry_price
            if rp.stop_loss_pct is not None and pnl_pct <= -rp.stop_loss_pct:
                self._position = "flat"
                return self._make_signal(event, OrderSide.BUY, f"Stop loss triggered ({pnl_pct:.2%})")
            if rp.take_profit_pct is not None and pnl_pct >= rp.take_profit_pct:
                self._position = "flat"
                return self._make_signal(event, OrderSide.BUY, f"Take profit triggered ({pnl_pct:.2%})")
        return None

    def _evaluate_condition(self, df: pd.DataFrame, cond: CompiledCondition) -> bool:
        """Evaluate a single condition against the current DataFrame."""
        last = len(df) - 1
        if last < 1:
            return False

        left_col = cond.column_name
        left_now = cast(float, df[left_col].iloc[last])
        left_prev = cast(float, df[left_col].iloc[last - 1])

        # Determine right-hand side value
        right_now: float
        right_prev: float
        if cond.comparator_indicator is not None:
            right_col = cond.comparator_column_name
            right_now = cast(float, df[right_col].iloc[last])
            right_prev = cast(float, df[right_col].iloc[last - 1])
        elif cond.comparator_value is not None:
            right_now = cond.comparator_value
            right_prev = cond.comparator_value
        else:
            return False

        # Check for NaN
        if pd.isna(left_now) or pd.isna(left_prev) or pd.isna(right_now) or pd.isna(right_prev):
            return False

        op = cond.operator
        if op == "crosses_above":
            return left_prev <= right_prev and left_now > right_now
        elif op == "crosses_below":
            return left_prev >= right_prev and left_now < right_now
        elif op == "greater_than":
            return left_now > right_now
        elif op == "less_than":
            return left_now < right_now
        elif op == "equal":
            return left_now == right_now
        else:
            return False

    def _make_signal(self, event: KlineEvent, side: OrderSide, reason: str) -> Signal:
        """Create a Signal from the current event context."""
        return Signal(
            strategy_id=self._compiled.config.id,
            symbol=event.symbol,
            side=side,
            strength=1.0,
            timestamp=int(time.time() * 1000),
            reason=reason,
        )

    def reset(self) -> None:
        """Reset the runtime state (bars, position)."""
        self._bars.clear()
        self._position = "flat"
        self._entry_price = 0.0
