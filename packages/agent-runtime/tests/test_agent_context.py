"""Tests for Batch 4: cost tracker, pruning, compaction, and budget."""

from __future__ import annotations

import time

import pytest

from pnlclaw_agent.context.budget import BudgetStatus, TokenBudget
from pnlclaw_agent.context.compaction import ContextCompactor
from pnlclaw_agent.context.pruning import ContextPruner
from pnlclaw_agent.cost.tracker import TokenCostTracker
from pnlclaw_types.agent import ChatMessage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg(role: str, content: str, age_seconds: float = 0) -> ChatMessage:
    """Create a ChatMessage with optional age offset."""
    ts = int((time.time() - age_seconds) * 1000)
    return ChatMessage(role=role, content=content, timestamp=ts)


# ---------------------------------------------------------------------------
# TokenCostTracker tests (J15)
# ---------------------------------------------------------------------------


class TestTokenCostTracker:
    def test_record_and_query(self) -> None:
        tracker = TokenCostTracker()
        tracker.record_usage("s1", "gpt-4o", 100, 50, 0.005, tool_name="market_ticker")
        tracker.record_usage("s1", "gpt-4o", 200, 100, 0.010)

        cost = tracker.get_session_cost("s1")
        assert cost["total_input_tokens"] == 300
        assert cost["total_output_tokens"] == 150
        assert cost["total_tokens"] == 450
        assert cost["total_cost_usd"] == pytest.approx(0.015)
        assert cost["call_count"] == 2
        assert "market_ticker" in cost["by_tool"]

    def test_empty_session(self) -> None:
        tracker = TokenCostTracker()
        cost = tracker.get_session_cost("nonexistent")
        assert cost["total_tokens"] == 0
        assert cost["call_count"] == 0

    def test_daily_cost(self) -> None:
        tracker = TokenCostTracker()
        tracker.record_usage("s1", "gpt-4o", 100, 50, 0.005)
        tracker.record_usage("s2", "gpt-4o", 200, 100, 0.010)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        cost = tracker.get_daily_cost(today)
        assert cost["call_count"] == 2
        assert cost["total_cost_usd"] == pytest.approx(0.015)

    def test_reset(self) -> None:
        tracker = TokenCostTracker()
        tracker.record_usage("s1", "gpt-4o", 100, 50, 0.005)
        assert tracker.total_records == 1
        tracker.reset()
        assert tracker.total_records == 0


# ---------------------------------------------------------------------------
# ContextPruner tests (J16)
# ---------------------------------------------------------------------------


class TestContextPruner:
    def test_no_stale_no_pruning(self) -> None:
        pruner = ContextPruner(ttl_seconds=300)
        msgs = [
            _msg("user", "hello"),
            _msg("tool", "result data"),
        ]
        result = pruner.prune(msgs, budget_tokens=100_000)
        assert len(result) == 2
        assert result[1].content == "result data"

    def test_stale_soft_trim(self) -> None:
        pruner = ContextPruner(ttl_seconds=60, soft_threshold=0.0)  # Always trigger soft
        big_content = "x" * 5000
        msgs = [
            _msg("user", "hello"),
            _msg("tool", big_content, age_seconds=120),  # 2 min old, > 60s TTL
        ]
        result = pruner.prune(msgs, budget_tokens=100_000)
        assert len(result) == 2
        assert "trimmed" in result[1].content
        assert len(result[1].content) < len(big_content)

    def test_stale_hard_clear(self) -> None:
        pruner = ContextPruner(ttl_seconds=60, soft_threshold=0.0, hard_threshold=0.0)
        msgs = [
            _msg("user", "hello"),
            _msg("tool", "x" * 5000, age_seconds=120),
        ]
        result = pruner.prune(msgs, budget_tokens=100_000)
        assert result[1].content == "[Old tool result cleared]"

    def test_system_messages_preserved(self) -> None:
        pruner = ContextPruner(ttl_seconds=1, soft_threshold=0.0, hard_threshold=0.0)
        msgs = [
            _msg("system", "prompt", age_seconds=600),
            _msg("tool", "data", age_seconds=120),
        ]
        result = pruner.prune(msgs, budget_tokens=100_000)
        assert result[0].role == "system"
        assert result[0].content == "prompt"

    def test_does_not_modify_input(self) -> None:
        pruner = ContextPruner(ttl_seconds=60, soft_threshold=0.0, hard_threshold=0.0)
        original = _msg("tool", "x" * 5000, age_seconds=120)
        msgs = [original]
        result = pruner.prune(msgs, budget_tokens=100_000)
        # Original should be unchanged
        assert len(original.content) == 5000
        assert result[0].content != original.content


# ---------------------------------------------------------------------------
# ContextCompactor tests (J17)
# ---------------------------------------------------------------------------


class TestContextCompactor:
    @pytest.mark.asyncio
    async def test_no_compaction_needed(self) -> None:
        compactor = ContextCompactor()
        msgs = [_msg("user", "hello"), _msg("assistant", "hi")]
        result = await compactor.compact(msgs, target_tokens=100_000)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_fallback_no_summarizer(self) -> None:
        compactor = ContextCompactor(summarizer=None)
        # Create many messages exceeding budget
        msgs = [_msg("user", "x" * 400) for _ in range(20)]
        result = await compactor.compact(msgs, target_tokens=100)
        # Should fall back to size-only compaction
        assert any("compacted" in m.content for m in result)

    @pytest.mark.asyncio
    async def test_with_mock_summarizer(self) -> None:
        class MockSummarizer:
            async def summarize(self, text: str) -> str:
                return "Summary of conversation."

        compactor = ContextCompactor(summarizer=MockSummarizer())
        msgs = [_msg("user", "x" * 400) for _ in range(20)]
        result = await compactor.compact(msgs, target_tokens=100)
        # Should have summaries or fallback
        assert len(result) < len(msgs)

    @pytest.mark.asyncio
    async def test_preserves_recent_messages(self) -> None:
        compactor = ContextCompactor()
        msgs = [_msg("user", f"msg {i}") for i in range(10)]
        result = await compactor.compact(msgs, target_tokens=10)
        # Last 6 messages should be protected
        assert any("msg 9" in m.content for m in result)


# ---------------------------------------------------------------------------
# TokenBudget tests (J18)
# ---------------------------------------------------------------------------


class TestTokenBudget:
    def test_ok_status(self) -> None:
        budget = TokenBudget(max_tokens=200_000, warning_threshold=32_000, hard_floor=16_000)
        assert budget.check_budget(100_000) == BudgetStatus.OK

    def test_warning_status(self) -> None:
        budget = TokenBudget(max_tokens=200_000, warning_threshold=32_000, hard_floor=16_000)
        # remaining = 200k - 175k = 25k, between hard_floor(16k) and warning(32k)
        assert budget.check_budget(175_000) == BudgetStatus.WARNING

    def test_critical_status(self) -> None:
        budget = TokenBudget(max_tokens=200_000, warning_threshold=32_000, hard_floor=16_000)
        # remaining = 200k - 190k = 10k, between 0 and hard_floor(16k)
        assert budget.check_budget(190_000) == BudgetStatus.CRITICAL

    def test_overflow_status(self) -> None:
        budget = TokenBudget(max_tokens=200_000, warning_threshold=32_000, hard_floor=16_000)
        assert budget.check_budget(200_001) == BudgetStatus.OVERFLOW

    def test_get_remaining(self) -> None:
        budget = TokenBudget(max_tokens=200_000)
        assert budget.get_remaining(150_000) == 50_000
        assert budget.get_remaining(250_000) == 0

    @pytest.mark.asyncio
    async def test_recover_prune_only(self) -> None:
        budget = TokenBudget(max_tokens=100, warning_threshold=50, hard_floor=20)
        pruner = ContextPruner(ttl_seconds=1)

        # Create messages that exceed budget
        msgs = [
            _msg("system", "prompt"),
            _msg("tool", "x" * 800, age_seconds=120),  # Old tool result
            _msg("user", "question"),
        ]
        current = sum(max(1, len(m.content) // 4) for m in msgs)

        result = await budget.recover(msgs, current, pruner)
        # Should have attempted to prune
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_recover_drops_oldest(self) -> None:
        budget = TokenBudget(max_tokens=50, warning_threshold=20, hard_floor=10)
        pruner = ContextPruner(ttl_seconds=300)  # Nothing stale

        # Create messages that exceed budget
        msgs = [
            _msg("user", "a" * 200),
            _msg("user", "b" * 200),
            _msg("user", "c" * 40),
        ]
        current = sum(max(1, len(m.content) // 4) for m in msgs)

        result = await budget.recover(msgs, current, pruner)
        # Should have dropped some messages
        assert len(result) < len(msgs)
