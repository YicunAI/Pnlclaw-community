"""Tests for 5 built-in risk rules (S2-H02)."""

from __future__ import annotations

import time
from typing import Any

from pnlclaw_risk.rules import (
    CooldownRule,
    DailyLossLimitRule,
    MaxPositionRule,
    MaxSingleRiskRule,
    SymbolBlacklistRule,
    create_default_rules,
)
from pnlclaw_types.agent import TradeIntent
from pnlclaw_types.trading import OrderSide, OrderType


def _make_intent(**overrides: Any) -> TradeIntent:
    defaults = {
        "symbol": "BTC/USDT",
        "side": OrderSide.BUY,
        "quantity": 0.1,
        "price": 67000.0,
        "order_type": OrderType.MARKET,
        "reasoning": "test",
        "confidence": 0.8,
        "risk_params": {"stop_loss": 65000.0, "take_profit": 70000.0},
        "timestamp": int(time.time() * 1000),
    }
    defaults.update(overrides)
    return TradeIntent(**defaults)


class TestMaxPositionRule:
    def test_allows_within_limit(self) -> None:
        rule = MaxPositionRule(max_position_pct=0.20)
        ctx = {"total_equity": 100_000.0, "positions": {"BTC/USDT": 5000.0}}
        intent = _make_intent(quantity=0.1, price=67000.0)  # 6700 + 5000 = 11700 < 20000
        result = rule.check(intent, ctx)
        assert result.allowed is True

    def test_blocks_over_limit(self) -> None:
        rule = MaxPositionRule(max_position_pct=0.10)
        ctx = {"total_equity": 100_000.0, "positions": {"BTC/USDT": 8000.0}}
        intent = _make_intent(quantity=0.1, price=67000.0)  # 6700 + 8000 = 14700 > 10000
        result = rule.check(intent, ctx)
        assert result.allowed is False
        assert "max_position" == result.rule_id

    def test_allows_when_no_equity(self) -> None:
        rule = MaxPositionRule()
        result = rule.check(_make_intent(), {"total_equity": 0})
        assert result.allowed is True


class TestMaxSingleRiskRule:
    def test_allows_within_limit(self) -> None:
        rule = MaxSingleRiskRule(max_risk_pct=0.02)
        ctx = {"total_equity": 100_000.0}
        intent = _make_intent(
            quantity=0.5,
            price=67000.0,
            risk_params={"stop_loss": 66800.0, "take_profit": 68000.0},
        )
        # loss = |67000 - 66800| * 0.5 = 100 < 2000
        result = rule.check(intent, ctx)
        assert result.allowed is True

    def test_blocks_over_limit(self) -> None:
        rule = MaxSingleRiskRule(max_risk_pct=0.02)
        ctx = {"total_equity": 100_000.0}
        intent = _make_intent(
            quantity=2.0,
            price=67000.0,
            risk_params={"stop_loss": 65000.0, "take_profit": 70000.0},
        )
        # loss = |67000 - 65000| * 2 = 4000 > 2000
        result = rule.check(intent, ctx)
        assert result.allowed is False


class TestDailyLossLimitRule:
    def test_allows_no_loss(self) -> None:
        rule = DailyLossLimitRule(max_daily_loss_pct=0.05)
        ctx = {"total_equity": 100_000.0, "daily_realized_pnl": 500.0}
        result = rule.check(_make_intent(), ctx)
        assert result.allowed is True

    def test_blocks_at_limit(self) -> None:
        rule = DailyLossLimitRule(max_daily_loss_pct=0.05)
        ctx = {"total_equity": 100_000.0, "daily_realized_pnl": -5000.0}
        result = rule.check(_make_intent(), ctx)
        assert result.allowed is False

    def test_blocks_over_limit(self) -> None:
        rule = DailyLossLimitRule(max_daily_loss_pct=0.05)
        ctx = {"total_equity": 100_000.0, "daily_realized_pnl": -6000.0}
        result = rule.check(_make_intent(), ctx)
        assert result.allowed is False


class TestSymbolBlacklistRule:
    def test_allows_non_blacklisted(self) -> None:
        rule = SymbolBlacklistRule(blacklist=["DOGE/USDT"])
        result = rule.check(_make_intent(symbol="BTC/USDT"), {})
        assert result.allowed is True

    def test_blocks_blacklisted(self) -> None:
        rule = SymbolBlacklistRule(blacklist=["BTC/USDT"])
        result = rule.check(_make_intent(symbol="BTC/USDT"), {})
        assert result.allowed is False

    def test_add_remove(self) -> None:
        rule = SymbolBlacklistRule()
        rule.add("XRP/USDT")
        assert "XRP/USDT" in rule.blacklist
        rule.remove("XRP/USDT")
        assert "XRP/USDT" not in rule.blacklist


class TestCooldownRule:
    def test_allows_first_trade(self) -> None:
        rule = CooldownRule(cooldown_seconds=300)
        result = rule.check(_make_intent(), {"last_trade_times": {}})
        assert result.allowed is True

    def test_blocks_during_cooldown(self) -> None:
        rule = CooldownRule(cooldown_seconds=300)
        ctx = {"last_trade_times": {"BTC/USDT": time.time() - 10}}
        result = rule.check(_make_intent(), ctx)
        assert result.allowed is False

    def test_allows_after_cooldown(self) -> None:
        rule = CooldownRule(cooldown_seconds=300)
        ctx = {"last_trade_times": {"BTC/USDT": time.time() - 400}}
        result = rule.check(_make_intent(), ctx)
        assert result.allowed is True


class TestCreateDefaultRules:
    def test_returns_five_rules(self) -> None:
        rules = create_default_rules()
        assert len(rules) == 5

    def test_all_enabled(self) -> None:
        rules = create_default_rules()
        for rule in rules:
            assert rule.enabled is True
