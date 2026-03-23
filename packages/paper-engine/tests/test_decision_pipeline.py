"""Tests for DecisionPipeline — end-to-end (S2-G07)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from pnlclaw_paper.decision_pipeline import (
    DecisionPipeline,
    PipelineAction,
    PipelineConfig,
)
from pnlclaw_paper.orders import PaperOrderManager
from pnlclaw_risk.engine import RiskEngine
from pnlclaw_risk.kill_switch import KillSwitch
from pnlclaw_types.strategy import Signal
from pnlclaw_types.trading import OrderSide


@pytest.fixture(autouse=True)
def _reset_ks() -> None:
    KillSwitch._reset_singleton()


def _make_signal(**overrides: Any) -> Signal:
    defaults = {
        "strategy_id": "strat-001",
        "symbol": "BTC/USDT",
        "side": OrderSide.BUY,
        "strength": 0.85,
        "timestamp": int(time.time() * 1000),
        "reason": "SMA cross",
    }
    defaults.update(overrides)
    return Signal(**defaults)


class TestDecisionPipeline:
    def _make_pipeline(
        self,
        tmp_path: Path,
        rules: list | None = None,
        kill_switch: bool = False,
    ) -> DecisionPipeline:
        ks_path = tmp_path / "ks.json"
        ks = KillSwitch(ks_path) if kill_switch else None
        engine = RiskEngine(rules or [])
        order_mgr = PaperOrderManager()
        config = PipelineConfig(
            dedupe_ttl_seconds=60.0,
            min_order_interval_seconds=0.0,  # no throttle for tests
            default_quantity=0.01,
            default_account_id="test-acc",
            enable_validation=False,  # no price provider in tests
        )
        return DecisionPipeline(
            risk_engine=engine,
            order_manager=order_mgr,
            kill_switch=ks,
            config=config,
        )

    def test_signal_executed(self, tmp_path: Path) -> None:
        pipeline = self._make_pipeline(tmp_path)
        result = pipeline.process_signal(_make_signal())
        assert result.action == PipelineAction.EXECUTED
        assert result.order_id is not None

    def test_duplicate_signal_skipped(self, tmp_path: Path) -> None:
        pipeline = self._make_pipeline(tmp_path)
        signal = _make_signal()
        r1 = pipeline.process_signal(signal)
        assert r1.action == PipelineAction.EXECUTED
        r2 = pipeline.process_signal(signal)
        assert r2.action == PipelineAction.SKIPPED
        assert "Duplicate" in r2.reason

    def test_kill_switch_blocks(self, tmp_path: Path) -> None:
        pipeline = self._make_pipeline(tmp_path, kill_switch=True)
        ks = KillSwitch(tmp_path / "ks.json")
        ks.activate("test")
        result = pipeline.process_signal(_make_signal())
        assert result.action == PipelineAction.BLOCKED
        assert "Kill switch" in result.reason

    def test_throttle_blocks(self, tmp_path: Path) -> None:
        engine = RiskEngine()
        order_mgr = PaperOrderManager()
        config = PipelineConfig(
            min_order_interval_seconds=9999.0,
            default_quantity=0.01,
            default_account_id="test-acc",
            enable_validation=False,
        )
        pipeline = DecisionPipeline(
            risk_engine=engine,
            order_manager=order_mgr,
            config=config,
        )
        s1 = _make_signal(timestamp=int(time.time() * 1000))
        r1 = pipeline.process_signal(s1)
        assert r1.action == PipelineAction.EXECUTED

        s2 = _make_signal(timestamp=int(time.time() * 1000) + 1)
        r2 = pipeline.process_signal(s2)
        assert r2.action == PipelineAction.SKIPPED
        assert "Throttled" in r2.reason

    def test_risk_blocked(self, tmp_path: Path) -> None:
        from pnlclaw_risk.rules import SymbolBlacklistRule
        rule = SymbolBlacklistRule(blacklist=["BTC/USDT"])
        pipeline = self._make_pipeline(tmp_path, rules=[rule])
        result = pipeline.process_signal(_make_signal())
        assert result.action == PipelineAction.BLOCKED
        assert "Risk denied" in result.reason

    def test_different_symbols_not_throttled(self, tmp_path: Path) -> None:
        engine = RiskEngine()
        order_mgr = PaperOrderManager()
        config = PipelineConfig(
            min_order_interval_seconds=9999.0,
            default_quantity=0.01,
            default_account_id="test-acc",
            enable_validation=False,
        )
        pipeline = DecisionPipeline(
            risk_engine=engine,
            order_manager=order_mgr,
            config=config,
        )
        r1 = pipeline.process_signal(_make_signal(symbol="BTC/USDT"))
        assert r1.action == PipelineAction.EXECUTED

        r2 = pipeline.process_signal(_make_signal(symbol="ETH/USDT"))
        assert r2.action == PipelineAction.EXECUTED
