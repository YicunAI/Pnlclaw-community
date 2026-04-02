"""Tests for Protocol interfaces, ComponentRegistry, and Community implementations.

Sprint 3.1 — Validates Protocol definitions, registry CRUD, Pro extension
replacement, and community basic implementations.
"""

from __future__ import annotations

import pytest

from pnlclaw_agent.implementations import (
    BasicContextManager,
    FixedModelRouter,
    KeywordMemoryBackend,
    RuleBasedFeedback,
    SingleAgentRunner,
)
from pnlclaw_agent.protocols import (
    AgentOrchestrator,
    ContextEngine,
    DelegationRequest,
    FeedbackEngine,
    MemoryBackend,
    MemoryEntry,
    ModelRouter,
)
from pnlclaw_agent.registry import ComponentRegistry

# ---------------------------------------------------------------------------
# Test 1: Protocol runtime_checkable validation
# ---------------------------------------------------------------------------


class TestProtocolCheckable:
    def test_memory_backend_is_checkable(self) -> None:
        backend = KeywordMemoryBackend()
        assert isinstance(backend, MemoryBackend)

    def test_orchestrator_is_checkable(self) -> None:
        runner = SingleAgentRunner()
        assert isinstance(runner, AgentOrchestrator)

    def test_model_router_is_checkable(self) -> None:
        router = FixedModelRouter()
        assert isinstance(router, ModelRouter)

    def test_context_engine_is_checkable(self) -> None:
        engine = BasicContextManager()
        assert isinstance(engine, ContextEngine)

    def test_feedback_engine_is_checkable(self) -> None:
        feedback = RuleBasedFeedback()
        assert isinstance(feedback, FeedbackEngine)


# ---------------------------------------------------------------------------
# Test 2: Registry register + get
# ---------------------------------------------------------------------------


class TestRegistryRegisterGet:
    def test_register_and_get(self) -> None:
        reg = ComponentRegistry()
        backend = KeywordMemoryBackend()
        reg.register("memory", backend)
        assert reg.get("memory") is backend

    def test_register_duplicate_raises(self) -> None:
        reg = ComponentRegistry()
        reg.register("memory", KeywordMemoryBackend())
        with pytest.raises(KeyError, match="already registered"):
            reg.register("memory", KeywordMemoryBackend())


# ---------------------------------------------------------------------------
# Test 3: Registry replace
# ---------------------------------------------------------------------------


class TestRegistryReplace:
    def test_replace_existing(self) -> None:
        reg = ComponentRegistry()
        old = KeywordMemoryBackend()
        new = KeywordMemoryBackend()
        reg.register("memory", old)
        reg.replace("memory", new)
        assert reg.get("memory") is new

    def test_replace_nonexistent_raises(self) -> None:
        reg = ComponentRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.replace("nonexistent", KeywordMemoryBackend())


# ---------------------------------------------------------------------------
# Test 4: Registry get unregistered raises KeyError
# ---------------------------------------------------------------------------


class TestRegistryGetUnregistered:
    def test_get_missing_raises(self) -> None:
        reg = ComponentRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.get("nonexistent")


# ---------------------------------------------------------------------------
# Test 5: list_registered
# ---------------------------------------------------------------------------


class TestRegistryListRegistered:
    def test_list_returns_correct_mapping(self) -> None:
        reg = ComponentRegistry()
        reg.register("memory", KeywordMemoryBackend())
        reg.register("router", FixedModelRouter())

        mapping = reg.list_registered()
        assert "memory" in mapping
        assert "router" in mapping
        assert mapping["memory"] == "KeywordMemoryBackend"
        assert mapping["router"] == "FixedModelRouter"

    def test_list_empty(self) -> None:
        reg = ComponentRegistry()
        assert reg.list_registered() == {}


# ---------------------------------------------------------------------------
# Test 6: PRO RESERVED methods raise NotImplementedError
# ---------------------------------------------------------------------------


class TestProReservedMethods:
    @pytest.mark.asyncio
    async def test_memory_semantic_recall_raises(self) -> None:
        backend = KeywordMemoryBackend()
        with pytest.raises(NotImplementedError, match="PnLClaw Pro"):
            await backend.semantic_recall("test")

    @pytest.mark.asyncio
    async def test_orchestrator_delegate_raises(self) -> None:
        runner = SingleAgentRunner()
        with pytest.raises(NotImplementedError, match="PnLClaw Pro"):
            await runner.delegate(DelegationRequest(task="test"))

    def test_model_router_select_for_task_raises(self) -> None:
        router = FixedModelRouter()
        with pytest.raises(NotImplementedError, match="PnLClaw Pro"):
            router.select_for_task("analysis")

    @pytest.mark.asyncio
    async def test_feedback_iterate_raises(self) -> None:
        feedback = RuleBasedFeedback()
        with pytest.raises(NotImplementedError, match="PnLClaw Pro"):
            from pnlclaw_agent.protocols import IterationPlan

            await feedback.iterate(IterationPlan(strategy_id="test"))


# ---------------------------------------------------------------------------
# Test 7: Community implementations functional tests
# ---------------------------------------------------------------------------


class TestCommunityImplementations:
    @pytest.mark.asyncio
    async def test_keyword_memory_store_and_recall(self) -> None:
        backend = KeywordMemoryBackend()
        await backend.store(MemoryEntry(id="1", content="BTC price analysis"))
        await backend.store(MemoryEntry(id="2", content="ETH strategy draft"))

        results = await backend.recall("BTC")
        assert len(results) == 1
        assert results[0].id == "1"

    @pytest.mark.asyncio
    async def test_keyword_memory_recall_empty(self) -> None:
        backend = KeywordMemoryBackend()
        results = await backend.recall("nothing")
        assert results == []

    @pytest.mark.asyncio
    async def test_single_agent_runner(self) -> None:
        runner = SingleAgentRunner()
        result = await runner.run("analyze BTC", {})
        assert "analyze BTC" in result

    def test_fixed_model_router(self) -> None:
        router = FixedModelRouter(model="gpt-4o")
        assert router.route([{"role": "user", "content": "hi"}]) == "gpt-4o"

    @pytest.mark.asyncio
    async def test_basic_context_manager(self) -> None:
        ctx = BasicContextManager()
        await ctx.bootstrap({"budget": 1000})
        await ctx.ingest({"type": "ticker", "data": "BTC=67000"})
        result = await ctx.assemble(10)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_rule_based_feedback(self) -> None:
        feedback = RuleBasedFeedback()
        result = await feedback.analyze({"sharpe_ratio": 1.5})
        assert "acceptable" in result.get("recommendation", "").lower()

    @pytest.mark.asyncio
    async def test_rule_based_feedback_negative_sharpe(self) -> None:
        feedback = RuleBasedFeedback()
        result = await feedback.analyze({"sharpe_ratio": -0.5})
        assert "underperforms" in result.get("recommendation", "").lower()


# ---------------------------------------------------------------------------
# Test 8: Registry is_registered and len
# ---------------------------------------------------------------------------


class TestRegistryUtilities:
    def test_is_registered(self) -> None:
        reg = ComponentRegistry()
        reg.register("memory", KeywordMemoryBackend())
        assert reg.is_registered("memory") is True
        assert reg.is_registered("nonexistent") is False

    def test_len(self) -> None:
        reg = ComponentRegistry()
        assert len(reg) == 0
        reg.register("a", KeywordMemoryBackend())
        reg.register("b", FixedModelRouter())
        assert len(reg) == 2
