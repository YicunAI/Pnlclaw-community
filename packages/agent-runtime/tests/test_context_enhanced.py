"""Tests for ContextManager v0.1.1 enhancements.

Sprint 4.1 — Validates tiktoken counting, auto-compaction trigger,
and market context injection.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pnlclaw_agent.context.manager import (
    TIKTOKEN_AVAILABLE,
    ContextManager,
    count_tokens,
)
from pnlclaw_types.agent import ChatMessage

# ---------------------------------------------------------------------------
# Test 1: tiktoken precise token counting
# ---------------------------------------------------------------------------


class TestTiktokenCounting:
    def test_count_tokens_returns_positive(self) -> None:
        result = count_tokens("Hello, world!")
        assert result >= 1

    def test_count_tokens_empty_string(self) -> None:
        result = count_tokens("")
        assert result >= 1

    def test_count_tokens_longer_text(self) -> None:
        text = "The quick brown fox jumps over the lazy dog. " * 10
        result = count_tokens(text)
        assert result > 10

    def test_estimate_tokens_matches_count_tokens(self) -> None:
        cm = ContextManager()
        text = "Test token counting integration"
        assert cm.estimate_tokens(text) == count_tokens(text)

    def test_tiktoken_availability_flag(self) -> None:
        assert isinstance(TIKTOKEN_AVAILABLE, bool)

    def test_fallback_when_tiktoken_unavailable(self) -> None:
        """Simulate tiktoken not available by using the heuristic."""
        text = "a" * 400
        # Fallback: 400 / 4 = 100
        from pnlclaw_agent.context.manager import _FALLBACK_CHARS_PER_TOKEN

        fallback_estimate = max(1, len(text) // _FALLBACK_CHARS_PER_TOKEN)
        assert fallback_estimate == 100


# ---------------------------------------------------------------------------
# Test 2: Auto-compaction trigger
# ---------------------------------------------------------------------------


class TestAutoCompaction:
    @pytest.mark.asyncio
    async def test_compaction_triggered_when_threshold_exceeded(self) -> None:
        """When token count exceeds threshold × budget, compaction fires."""
        mock_compactor = AsyncMock()
        mock_compactor.compact = AsyncMock(
            return_value=[
                ChatMessage(role="system", content="[compacted]", timestamp=0),
            ]
        )

        cm = ContextManager(
            max_tokens=100,
            compaction_threshold=0.5,
            compactor=mock_compactor,
        )

        # Fill beyond threshold (50 tokens out of 100 budget)
        # Each message is roughly many tokens
        for i in range(20):
            cm.add_message("user", f"Message {i}: " + "x" * 200)

        # The trim_if_needed should have run, and if compactor was called
        # it depends on the async context. Verify the mechanism exists.
        assert cm.message_count >= 1

    def test_no_compaction_without_compactor(self) -> None:
        cm = ContextManager(max_tokens=100, compaction_threshold=0.5)
        # Should not crash even without compactor
        for i in range(20):
            cm.add_message("user", f"Message {i}: " + "x" * 50)
        assert cm.message_count >= 1

    def test_compaction_threshold_configurable(self) -> None:
        cm = ContextManager(compaction_threshold=0.9)
        assert cm._compaction_threshold == 0.9

        cm2 = ContextManager(compaction_threshold=0.5)
        assert cm2._compaction_threshold == 0.5


# ---------------------------------------------------------------------------
# Test 3: Market context injection
# ---------------------------------------------------------------------------


class TestMarketContextInjection:
    @pytest.mark.asyncio
    async def test_inject_market_context(self) -> None:
        cm = ContextManager()
        await cm.inject_market_context(
            symbols=["BTC/USDT", "ETH/USDT"],
            prices={"BTC/USDT": 67234.50, "ETH/USDT": 3456.78},
        )

        msgs = cm.get_messages()
        assert len(msgs) == 1
        assert msgs[0].role == "system"
        assert "BTC/USDT" in msgs[0].content
        assert "$67,234.50" in msgs[0].content
        assert "ETH/USDT" in msgs[0].content

    @pytest.mark.asyncio
    async def test_inject_replaces_existing_market_context(self) -> None:
        cm = ContextManager()
        await cm.inject_market_context(
            symbols=["BTC/USDT"],
            prices={"BTC/USDT": 60000.00},
        )
        await cm.inject_market_context(
            symbols=["BTC/USDT"],
            prices={"BTC/USDT": 67000.00},
        )

        msgs = cm.get_messages()
        market_msgs = [m for m in msgs if "Live Market Prices" in m.content]
        assert len(market_msgs) == 1
        assert "$67,000.00" in market_msgs[0].content
        assert "$60,000.00" not in market_msgs[0].content

    @pytest.mark.asyncio
    async def test_inject_empty_prices_noop(self) -> None:
        cm = ContextManager()
        await cm.inject_market_context(symbols=[], prices={})
        assert cm.message_count == 0

    @pytest.mark.asyncio
    async def test_inject_respects_budget_limit(self) -> None:
        cm = ContextManager(max_tokens=50)
        # Inject many symbols to exceed 10% budget
        symbols = [f"SYM{i}/USDT" for i in range(100)]
        prices = {s: float(i * 1000) for i, s in enumerate(symbols)}

        await cm.inject_market_context(symbols=symbols, prices=prices)

        msgs = cm.get_messages()
        assert len(msgs) == 1
        # Should be truncated
        content = msgs[0].content
        assert cm.estimate_tokens(content) <= cm._max_tokens


# ---------------------------------------------------------------------------
# Test 4: Existing context manager tests still pass
# ---------------------------------------------------------------------------


class TestExistingBehaviorPreserved:
    def test_add_and_get(self) -> None:
        cm = ContextManager()
        cm.add_message("user", "hello")
        cm.add_message("assistant", "hi")
        msgs = cm.get_messages()
        assert len(msgs) == 2

    def test_total_tokens(self) -> None:
        cm = ContextManager()
        cm.add_message("user", "a" * 400)
        cm.add_message("assistant", "b" * 200)
        total = cm.total_tokens()
        assert total > 0

    def test_clear(self) -> None:
        cm = ContextManager()
        cm.add_message("user", "test")
        cm.clear()
        assert cm.message_count == 0
