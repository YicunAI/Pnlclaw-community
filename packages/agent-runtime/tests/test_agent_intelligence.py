"""Tests for Batch 3: PnL attribution, trading memory, and user preferences."""

from __future__ import annotations

from pathlib import Path

import pytest

from pnlclaw_agent.attribution.engine import PnLAttributionEngine
from pnlclaw_agent.memory.preferences import (
    RiskAppetite,
    UserPreferences,
    load_preferences,
    save_preferences,
    update_preference,
)
from pnlclaw_agent.memory.trading_memory import TradingMemory
from pnlclaw_types.agent import ChatMessage

# ---------------------------------------------------------------------------
# Sample trade data
# ---------------------------------------------------------------------------

_TRADES = [
    {
        "strategy_id": "strat-001",
        "pnl": 500.0,
        "entry_time": 1_704_067_200_000,  # 2024-01-01
        "exit_time": 1_704_153_600_000,  # 2024-01-02
        "symbol": "BTC/USDT",
        "side": "buy",
        "quantity": 0.5,
        "entry_price": 42000.0,
        "exit_price": 43000.0,
        "commission": 10.0,
        "slippage": 5.0,
        "fees": 2.0,
    },
    {
        "strategy_id": "strat-001",
        "pnl": -200.0,
        "entry_time": 1_704_240_000_000,  # 2024-01-03
        "exit_time": 1_704_326_400_000,  # 2024-01-04
        "symbol": "ETH/USDT",
        "side": "buy",
        "quantity": 2.0,
        "entry_price": 2200.0,
        "exit_price": 2100.0,
        "commission": 8.0,
        "slippage": 3.0,
        "fees": 1.5,
    },
    {
        "strategy_id": "strat-002",
        "pnl": 800.0,
        "entry_time": 1_704_412_800_000,  # 2024-01-05
        "exit_time": 1_704_499_200_000,  # 2024-01-06
        "symbol": "BTC/USDT",
        "side": "sell",
        "quantity": 1.0,
        "entry_price": 44000.0,
        "exit_price": 43200.0,
        "commission": 12.0,
        "slippage": 4.0,
        "fees": 2.5,
    },
    {
        "strategy_id": "strat-002",
        "pnl": -100.0,
        "entry_time": 1_704_585_600_000,  # 2024-01-07
        "exit_time": 1_704_672_000_000,  # 2024-01-08
        "symbol": "ETH/USDT",
        "side": "sell",
        "quantity": 3.0,
        "entry_price": 2150.0,
        "exit_price": 2183.33,
        "commission": 6.0,
        "slippage": 2.0,
        "fees": 1.0,
    },
]


# ---------------------------------------------------------------------------
# PnL Attribution tests (J12)
# ---------------------------------------------------------------------------


class TestPnLAttributionEngine:
    def test_explain_basic(self) -> None:
        engine = PnLAttributionEngine()
        result = engine.explain(_TRADES)

        assert result.total_pnl == pytest.approx(1000.0)
        assert "strat-001" in result.by_strategy
        assert "strat-002" in result.by_strategy
        assert result.by_strategy["strat-001"] == pytest.approx(300.0)
        assert result.by_strategy["strat-002"] == pytest.approx(700.0)

    def test_explain_by_period(self) -> None:
        engine = PnLAttributionEngine()
        result = engine.explain(_TRADES)
        # All trades are in the same ISO week (2024-W01)
        assert len(result.by_period) >= 1

    def test_explain_by_event(self) -> None:
        engine = PnLAttributionEngine()
        result = engine.explain(_TRADES)
        # Should have both wins and losses
        win_events = [e for e in result.by_event if e["type"] == "win"]
        loss_events = [e for e in result.by_event if e["type"] == "loss"]
        assert len(win_events) >= 1
        assert len(loss_events) >= 1

    def test_explain_by_cost(self) -> None:
        engine = PnLAttributionEngine()
        result = engine.explain(_TRADES)
        assert result.by_cost["commissions"] == pytest.approx(36.0)
        assert result.by_cost["slippage"] == pytest.approx(14.0)
        assert result.by_cost["fees"] == pytest.approx(7.0)

    def test_explain_empty(self) -> None:
        engine = PnLAttributionEngine()
        result = engine.explain([])
        assert result.total_pnl == 0.0
        assert result.by_strategy == {}

    def test_explain_with_period_filter(self) -> None:
        engine = PnLAttributionEngine()
        # Only include trades from Jan 1-4
        result = engine.explain(
            _TRADES,
            period=("2024-01-01", "2024-01-04"),
        )
        # Should include first 2 trades only
        assert result.total_pnl == pytest.approx(300.0)

    def test_generate_narrative(self) -> None:
        engine = PnLAttributionEngine()
        attribution = engine.explain(_TRADES)
        narrative = engine.generate_narrative(attribution)

        assert "PnL Report" in narrative
        assert "strat-001" in narrative
        assert "strat-002" in narrative
        assert "Costs:" in narrative

    def test_period_detection(self) -> None:
        engine = PnLAttributionEngine()
        result = engine.explain(_TRADES)
        assert result.period_start != ""
        assert result.period_end != ""


# ---------------------------------------------------------------------------
# TradingMemory tests (J13)
# ---------------------------------------------------------------------------


class TestTradingMemory:
    def test_save_and_list(self, tmp_path: Path) -> None:
        mem = TradingMemory(memory_dir=tmp_path)
        msgs = [
            ChatMessage(role="user", content="Analyze BTC/USDT", timestamp=1_700_000_000_000),
            ChatMessage(role="assistant", content="BTC is trending up", timestamp=1_700_000_001_000),
        ]
        mem.save_context("session-001", msgs, summary="BTC analysis session")

        sessions = mem.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "session-001"
        assert sessions[0]["summary"] == "BTC analysis session"

    def test_auto_summary(self, tmp_path: Path) -> None:
        mem = TradingMemory(memory_dir=tmp_path)
        msgs = [
            ChatMessage(role="user", content="Check ETH price", timestamp=1_700_000_000_000),
        ]
        mem.save_context("session-002", msgs)

        sessions = mem.list_sessions()
        assert "Check ETH price" in sessions[0]["summary"]

    def test_recall_by_symbol(self, tmp_path: Path) -> None:
        mem = TradingMemory(memory_dir=tmp_path)
        msgs = [
            ChatMessage(role="user", content="Analyze BTC/USDT trend", timestamp=1_700_000_000_000),
        ]
        mem.save_context("session-001", msgs, summary="BTC/USDT trend analysis")

        # Recall with matching symbol
        result = mem.recall_for_prompt({"symbols": ["BTC/USDT"]})
        assert "BTC/USDT" in result

        # Recall with non-matching symbol
        result2 = mem.recall_for_prompt({"symbols": ["DOGE/USDT"]})
        assert result2 == ""

    def test_recall_empty(self, tmp_path: Path) -> None:
        mem = TradingMemory(memory_dir=tmp_path)
        result = mem.recall_for_prompt({"symbols": ["BTC/USDT"]})
        assert result == ""

    def test_clear(self, tmp_path: Path) -> None:
        mem = TradingMemory(memory_dir=tmp_path)
        msgs = [ChatMessage(role="user", content="test", timestamp=1_700_000_000_000)]
        mem.save_context("s1", msgs)
        mem.save_context("s2", msgs)
        assert len(mem.list_sessions()) == 2

        mem.clear()
        assert len(mem.list_sessions()) == 0


# ---------------------------------------------------------------------------
# UserPreferences tests (J14)
# ---------------------------------------------------------------------------


class TestUserPreferences:
    def test_defaults(self) -> None:
        prefs = UserPreferences()
        assert prefs.risk_appetite == RiskAppetite.MODERATE
        assert prefs.preferred_symbols == []
        assert prefs.preferred_timeframes == []
        assert prefs.preferred_strategy_types == []

    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "prefs.json"
        prefs = UserPreferences(
            risk_appetite=RiskAppetite.AGGRESSIVE,
            preferred_symbols=["BTC/USDT", "ETH/USDT"],
            preferred_timeframes=["1h", "4h"],
            preferred_strategy_types=["sma_cross"],
        )
        save_preferences(prefs, path)

        loaded = load_preferences(path)
        assert loaded.risk_appetite == RiskAppetite.AGGRESSIVE
        assert loaded.preferred_symbols == ["BTC/USDT", "ETH/USDT"]
        assert loaded.preferred_timeframes == ["1h", "4h"]

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        prefs = load_preferences(path)
        assert prefs.risk_appetite == RiskAppetite.MODERATE

    def test_update_preference(self, tmp_path: Path) -> None:
        path = tmp_path / "prefs.json"
        save_preferences(UserPreferences(), path)

        updated = update_preference("risk_appetite", RiskAppetite.CONSERVATIVE, path)
        assert updated.risk_appetite == RiskAppetite.CONSERVATIVE

        # Verify persistence
        loaded = load_preferences(path)
        assert loaded.risk_appetite == RiskAppetite.CONSERVATIVE

    def test_update_list_preference(self, tmp_path: Path) -> None:
        path = tmp_path / "prefs.json"
        save_preferences(UserPreferences(), path)

        updated = update_preference("preferred_symbols", ["SOL/USDT"], path)
        assert updated.preferred_symbols == ["SOL/USDT"]

    def test_update_invalid_key(self, tmp_path: Path) -> None:
        path = tmp_path / "prefs.json"
        save_preferences(UserPreferences(), path)

        with pytest.raises(ValueError, match="Unknown preference"):
            update_preference("nonexistent_key", "value", path)
