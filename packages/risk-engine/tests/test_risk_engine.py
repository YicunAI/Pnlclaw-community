"""Tests for risk engine core (S2-H01)."""

from __future__ import annotations

import time
from typing import Any

from pnlclaw_risk.engine import RiskEngine
from pnlclaw_types.agent import TradeIntent
from pnlclaw_types.risk import RiskDecision, RiskLevel
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


class _AllowRule:
    rule_id = "allow_all"
    enabled = True

    def check(self, intent: TradeIntent, context: dict[str, Any]) -> RiskDecision:
        return RiskDecision(
            rule_id=self.rule_id,
            allowed=True,
            level=RiskLevel.SAFE,
            reason="",
            timestamp=int(time.time() * 1000),
        )


class _BlockRule:
    rule_id = "block_all"
    enabled = True

    def check(self, intent: TradeIntent, context: dict[str, Any]) -> RiskDecision:
        return RiskDecision(
            rule_id=self.rule_id,
            allowed=False,
            level=RiskLevel.BLOCKED,
            reason="Blocked by test rule",
            timestamp=int(time.time() * 1000),
        )


class _DisabledBlockRule:
    rule_id = "disabled"
    enabled = False

    def check(self, intent: TradeIntent, context: dict[str, Any]) -> RiskDecision:
        return RiskDecision(
            rule_id=self.rule_id,
            allowed=False,
            level=RiskLevel.BLOCKED,
            reason="Should not run",
            timestamp=int(time.time() * 1000),
        )


class TestRiskEngine:
    def test_no_rules_allows(self) -> None:
        engine = RiskEngine()
        result = engine.pre_check(_make_intent())
        assert result.allowed is True

    def test_all_rules_pass(self) -> None:
        engine = RiskEngine([_AllowRule(), _AllowRule()])
        result = engine.pre_check(_make_intent())
        assert result.allowed is True

    def test_single_block_denies(self) -> None:
        engine = RiskEngine([_AllowRule(), _BlockRule()])
        result = engine.pre_check(_make_intent())
        assert result.allowed is False
        assert "block_all" in result.rule_id

    def test_disabled_rule_skipped(self) -> None:
        engine = RiskEngine([_DisabledBlockRule()])
        result = engine.pre_check(_make_intent())
        assert result.allowed is True

    def test_add_remove_rule(self) -> None:
        engine = RiskEngine()
        engine.add_rule(_BlockRule())
        assert len(engine.rules) == 1
        engine.remove_rule("block_all")
        assert len(engine.rules) == 0

    def test_multiple_blocks_aggregated(self) -> None:
        block1 = _BlockRule()
        block1.rule_id = "block1"
        block2 = _BlockRule()
        block2.rule_id = "block2"
        engine = RiskEngine([block1, block2])
        result = engine.pre_check(_make_intent())
        assert result.allowed is False
        assert "block1" in result.rule_id
        assert "block2" in result.rule_id

    def test_worst_level_propagated(self) -> None:
        class RestrictedRule:
            rule_id = "restricted"
            enabled = True

            def check(self, intent: TradeIntent, context: dict[str, Any]) -> RiskDecision:
                return RiskDecision(
                    rule_id=self.rule_id,
                    allowed=False,
                    level=RiskLevel.RESTRICTED,
                    reason="restricted",
                    timestamp=int(time.time() * 1000),
                )

        engine = RiskEngine([RestrictedRule(), _BlockRule()])
        result = engine.pre_check(_make_intent())
        assert result.level == RiskLevel.BLOCKED
