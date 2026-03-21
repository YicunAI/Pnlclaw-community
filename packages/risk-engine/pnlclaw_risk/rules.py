"""Built-in risk rules for PnLClaw risk engine.

Each rule implements the RiskRuleProtocol defined in engine.py:
  check(intent, context) → RiskDecision

Five rules:
  1. MaxPositionRule      — single symbol max position (default 20% of total equity)
  2. MaxSingleRiskRule    — single trade max loss (default 2% of total equity)
  3. DailyLossLimitRule   — daily loss cap (default 5% of total equity)
  4. SymbolBlacklistRule  — blocked trading pairs
  5. CooldownRule         — per-symbol trade cooldown (default 300 s)
"""

from __future__ import annotations

import time
from typing import Any

from pnlclaw_types.agent import TradeIntent
from pnlclaw_types.risk import RiskDecision, RiskLevel


def _now_ms() -> int:
    return int(time.time() * 1000)


def _allow(rule_id: str) -> RiskDecision:
    return RiskDecision(
        rule_id=rule_id,
        allowed=True,
        level=RiskLevel.SAFE,
        reason="",
        timestamp=_now_ms(),
    )


def _deny(rule_id: str, level: RiskLevel, reason: str) -> RiskDecision:
    return RiskDecision(
        rule_id=rule_id,
        allowed=False,
        level=level,
        reason=reason,
        timestamp=_now_ms(),
    )


# ---------------------------------------------------------------------------
# 1. MaxPositionRule
# ---------------------------------------------------------------------------


class MaxPositionRule:
    """Limits single-symbol position to a fraction of total equity.

    Context keys:
        total_equity (float): Total account equity.
        positions (dict[str, float]): symbol → current position value.
    """

    def __init__(self, max_position_pct: float = 0.20, *, enabled: bool = True) -> None:
        self._max_pct = max_position_pct
        self._enabled = enabled

    @property
    def rule_id(self) -> str:
        return "max_position"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def check(self, intent: TradeIntent, context: dict[str, Any]) -> RiskDecision:
        total_equity: float = context.get("total_equity", 0.0)
        if total_equity <= 0:
            return _allow(self.rule_id)

        positions: dict[str, float] = context.get("positions", {})
        current_value = positions.get(intent.symbol, 0.0)
        intent_value = intent.quantity * (intent.price or 0.0)
        new_value = current_value + intent_value
        max_value = total_equity * self._max_pct

        if new_value > max_value:
            return _deny(
                self.rule_id,
                RiskLevel.RESTRICTED,
                f"Position {intent.symbol} would be {new_value:.2f} "
                f"({new_value / total_equity:.1%} of equity), "
                f"max allowed {self._max_pct:.0%}",
            )
        return _allow(self.rule_id)


# ---------------------------------------------------------------------------
# 2. MaxSingleRiskRule
# ---------------------------------------------------------------------------


class MaxSingleRiskRule:
    """Limits single-trade max potential loss.

    Uses stop_loss from intent.risk_params to compute worst-case loss.

    Context keys:
        total_equity (float): Total account equity.
    """

    def __init__(self, max_risk_pct: float = 0.02, *, enabled: bool = True) -> None:
        self._max_pct = max_risk_pct
        self._enabled = enabled

    @property
    def rule_id(self) -> str:
        return "max_single_risk"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def check(self, intent: TradeIntent, context: dict[str, Any]) -> RiskDecision:
        total_equity: float = context.get("total_equity", 0.0)
        if total_equity <= 0:
            return _allow(self.rule_id)

        stop_loss: float | None = intent.risk_params.get("stop_loss")
        entry_price = intent.price or context.get("current_price", 0.0)
        if not stop_loss or not entry_price:
            return _allow(self.rule_id)

        loss_per_unit = abs(entry_price - stop_loss)
        potential_loss = loss_per_unit * intent.quantity
        max_allowed = total_equity * self._max_pct

        if potential_loss > max_allowed:
            return _deny(
                self.rule_id,
                RiskLevel.RESTRICTED,
                f"Potential loss {potential_loss:.2f} "
                f"({potential_loss / total_equity:.1%} of equity) "
                f"exceeds max {self._max_pct:.0%}",
            )
        return _allow(self.rule_id)


# ---------------------------------------------------------------------------
# 3. DailyLossLimitRule
# ---------------------------------------------------------------------------


class DailyLossLimitRule:
    """Blocks trading if daily realized losses exceed a threshold.

    Context keys:
        total_equity (float): Total account equity.
        daily_realized_pnl (float): Today's realized PnL (negative = loss).
    """

    def __init__(self, max_daily_loss_pct: float = 0.05, *, enabled: bool = True) -> None:
        self._max_pct = max_daily_loss_pct
        self._enabled = enabled

    @property
    def rule_id(self) -> str:
        return "daily_loss_limit"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def check(self, intent: TradeIntent, context: dict[str, Any]) -> RiskDecision:
        total_equity: float = context.get("total_equity", 0.0)
        if total_equity <= 0:
            return _allow(self.rule_id)

        daily_pnl: float = context.get("daily_realized_pnl", 0.0)
        max_loss = total_equity * self._max_pct

        if daily_pnl < 0 and abs(daily_pnl) >= max_loss:
            return _deny(
                self.rule_id,
                RiskLevel.DANGEROUS,
                f"Daily loss {abs(daily_pnl):.2f} "
                f"({abs(daily_pnl) / total_equity:.1%} of equity) "
                f"reached limit {self._max_pct:.0%}",
            )
        return _allow(self.rule_id)


# ---------------------------------------------------------------------------
# 4. SymbolBlacklistRule
# ---------------------------------------------------------------------------


class SymbolBlacklistRule:
    """Blocks trading on blacklisted symbols."""

    def __init__(
        self, blacklist: list[str] | None = None, *, enabled: bool = True
    ) -> None:
        self._blacklist: set[str] = set(blacklist) if blacklist else set()
        self._enabled = enabled

    @property
    def rule_id(self) -> str:
        return "symbol_blacklist"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def add(self, symbol: str) -> None:
        """Add a symbol to the blacklist."""
        self._blacklist.add(symbol)

    def remove(self, symbol: str) -> None:
        """Remove a symbol from the blacklist."""
        self._blacklist.discard(symbol)

    @property
    def blacklist(self) -> set[str]:
        return set(self._blacklist)

    def check(self, intent: TradeIntent, context: dict[str, Any]) -> RiskDecision:
        if intent.symbol in self._blacklist:
            return _deny(
                self.rule_id,
                RiskLevel.BLOCKED,
                f"Symbol {intent.symbol} is blacklisted",
            )
        return _allow(self.rule_id)


# ---------------------------------------------------------------------------
# 5. CooldownRule
# ---------------------------------------------------------------------------


class CooldownRule:
    """Enforces minimum time between trades on the same symbol.

    Context keys:
        last_trade_times (dict[str, float]): symbol → last trade epoch seconds.
    """

    def __init__(self, cooldown_seconds: float = 300.0, *, enabled: bool = True) -> None:
        self._cooldown = cooldown_seconds
        self._enabled = enabled

    @property
    def rule_id(self) -> str:
        return "cooldown"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def check(self, intent: TradeIntent, context: dict[str, Any]) -> RiskDecision:
        last_trade_times: dict[str, float] = context.get("last_trade_times", {})
        last_time = last_trade_times.get(intent.symbol)
        if last_time is None:
            return _allow(self.rule_id)

        now = time.time()
        elapsed = now - last_time
        if elapsed < self._cooldown:
            remaining = self._cooldown - elapsed
            return _deny(
                self.rule_id,
                RiskLevel.RESTRICTED,
                f"Cooldown active for {intent.symbol}: "
                f"{remaining:.0f}s remaining (min {self._cooldown:.0f}s)",
            )
        return _allow(self.rule_id)


# ---------------------------------------------------------------------------
# Convenience: default rule set
# ---------------------------------------------------------------------------


def create_default_rules() -> list[MaxPositionRule | MaxSingleRiskRule | DailyLossLimitRule | SymbolBlacklistRule | CooldownRule]:
    """Create the standard five risk rules with default parameters."""
    return [
        MaxPositionRule(),
        MaxSingleRiskRule(),
        DailyLossLimitRule(),
        SymbolBlacklistRule(),
        CooldownRule(),
    ]
