"""Tests for Batch 2: prompt builder, context manager, runtime, and roles."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from pnlclaw_agent.context.manager import ContextManager
from pnlclaw_agent.prompt_builder import AgentContext, build_system_prompt
from pnlclaw_agent.runtime import AgentRuntime, LegacyAgentRuntime
from pnlclaw_agent.team.roles import AGENT_ROLES, RoleDefinition, get_role
from pnlclaw_agent.tool_catalog import ToolCatalog
from pnlclaw_agent.tools.base import BaseTool, ToolResult
from pnlclaw_types.agent import AgentRole, AgentStreamEventType, MarketRegime, MarketState
from pnlclaw_types.risk import RiskLevel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(name: str, output: str = "OK") -> BaseTool:
    class _T(BaseTool):
        @property
        def name(self) -> str:
            return name

        @property
        def description(self) -> str:
            return f"Test tool {name}"

        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {}, "required": []}

        @property
        def risk_level(self) -> RiskLevel:
            return RiskLevel.SAFE

        def execute(self, args: dict[str, Any]) -> ToolResult:
            return ToolResult(output=output)

    return _T()


class MockLLM:
    """Mock LLM that returns pre-configured responses from a list.

    ``chat()`` serializes each response dict to JSON so the runtime's
    ``_parse_response`` can extract ``tool_calls`` / ``response`` fields.
    """

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    async def chat(self, messages: list[Any], **kwargs: Any) -> str:
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            import json
            return json.dumps(resp)
        return '{"response": "No more responses configured."}'

    async def chat_stream(self, messages: list[Any], **kwargs: Any) -> AsyncIterator[str]:
        text = await self.chat(messages, **kwargs)
        yield text

    async def chat_with_tools(
        self, messages: list[Any], tools: list[dict[str, Any]] | None = None, **kwargs: Any
    ) -> Any:
        from pnlclaw_llm.schemas import ToolCall, ToolCallResult, TokenUsage

        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            raw_calls = resp.get("tool_calls", [])
            parsed_calls = [
                ToolCall(
                    id=f"mock_call_{i}",
                    name=tc.get("tool", tc.get("name", "")),
                    arguments=tc.get("arguments", {}),
                )
                for i, tc in enumerate(raw_calls)
                if isinstance(tc, dict)
            ]
            text = resp.get("response", "") or None
            return ToolCallResult(
                tool_calls=parsed_calls,
                text=text,
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        return ToolCallResult(text="No more responses configured.")

    async def generate_structured(
        self, messages: list[Any], output_schema: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        return {"response": "No more responses configured."}


# ---------------------------------------------------------------------------
# PromptBuilder tests (J08)
# ---------------------------------------------------------------------------


class TestPromptBuilder:
    def test_base_prompt(self) -> None:
        ctx = AgentContext()
        prompt = build_system_prompt(ctx)
        assert "PnLClaw" in prompt
        assert "Safety" in prompt

    def test_with_tools(self) -> None:
        ctx = AgentContext(
            available_tools=[
                {
                    "name": "market_ticker",
                    "description": "Get ticker",
                    "parameters": {
                        "type": "object",
                        "properties": {"symbol": {"type": "string", "description": "Pair"}},
                        "required": ["symbol"],
                    },
                },
            ]
        )
        prompt = build_system_prompt(ctx)
        assert "market_ticker" in prompt
        assert "symbol" in prompt

    def test_with_market_state(self) -> None:
        ctx = AgentContext(
            market_state=MarketState(
                symbol="BTC/USDT",
                regime=MarketRegime.TRENDING,
                trend_strength=0.8,
                volatility=0.3,
                timestamp=1_700_000_000_000,
            )
        )
        prompt = build_system_prompt(ctx)
        assert "BTC/USDT" in prompt
        assert "trending" in prompt.lower()

    def test_with_user_preferences(self) -> None:
        ctx = AgentContext(
            user_preferences={
                "risk_appetite": "conservative",
                "preferred_symbols": ["BTC/USDT", "ETH/USDT"],
            }
        )
        prompt = build_system_prompt(ctx)
        assert "conservative" in prompt
        assert "BTC/USDT" in prompt

    def test_with_role(self) -> None:
        ctx = AgentContext(role=AgentRole.MARKET_ANALYST)
        prompt = build_system_prompt(ctx)
        assert "Market Analyst" in prompt

    def test_with_memory_context(self) -> None:
        ctx = AgentContext(memory_context="User prefers SMA cross strategies on BTC.")
        prompt = build_system_prompt(ctx)
        assert "SMA cross" in prompt

    def test_with_active_symbols(self) -> None:
        ctx = AgentContext(active_symbols=["BTC/USDT", "ETH/USDT"])
        prompt = build_system_prompt(ctx)
        assert "BTC/USDT" in prompt


# ---------------------------------------------------------------------------
# ContextManager tests (J10)
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_add_and_get(self) -> None:
        cm = ContextManager()
        cm.add_message("user", "hello")
        cm.add_message("assistant", "hi")
        msgs = cm.get_messages()
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"

    def test_estimate_tokens(self) -> None:
        cm = ContextManager()
        assert cm.estimate_tokens("abcd") >= 1
        token_count = cm.estimate_tokens("a" * 400)
        assert token_count > 0

    def test_total_tokens(self) -> None:
        cm = ContextManager()
        cm.add_message("user", "a" * 400)
        cm.add_message("assistant", "b" * 200)
        assert cm.total_tokens() > 0

    def test_auto_trim_by_message_count(self) -> None:
        cm = ContextManager(max_messages=5)
        for i in range(10):
            cm.add_message("user", f"msg {i}")
        assert cm.message_count <= 5

    def test_auto_trim_by_tokens(self) -> None:
        cm = ContextManager(max_tokens=100)
        # Each message ~100 tokens (400 chars)
        cm.add_message("user", "a" * 400)
        cm.add_message("user", "b" * 400)
        # Should trim to fit within 100 tokens
        assert cm.total_tokens() <= 100

    def test_system_messages_preserved(self) -> None:
        cm = ContextManager(max_messages=3)
        cm.add_message("system", "sys prompt")
        for i in range(5):
            cm.add_message("user", f"msg {i}")
        msgs = cm.get_messages()
        # System message should still be there
        assert any(m.role == "system" for m in msgs)

    def test_truncate_tool_result(self) -> None:
        cm = ContextManager(max_tokens=1000)
        # 30% of 1000 tokens = 300 tokens = 1200 chars
        big_content = "x" * 5000
        truncated = cm.truncate_tool_result(big_content)
        assert len(truncated) < len(big_content)
        assert "Truncated" in truncated

    def test_no_truncate_small_result(self) -> None:
        cm = ContextManager(max_tokens=100_000)
        small = "hello world"
        assert cm.truncate_tool_result(small) == small

    def test_clear(self) -> None:
        cm = ContextManager()
        cm.add_message("user", "test")
        cm.clear()
        assert cm.message_count == 0


# ---------------------------------------------------------------------------
# Agent Roles tests (J11)
# ---------------------------------------------------------------------------


class TestAgentRoles:
    def test_all_roles_defined(self) -> None:
        assert "market_analyst" in AGENT_ROLES
        assert "strategy_architect" in AGENT_ROLES
        assert "risk_guardian" in AGENT_ROLES

    def test_role_has_prompt(self) -> None:
        for role_def in AGENT_ROLES.values():
            assert len(role_def.system_prompt) > 50
            assert role_def.name
            assert role_def.description

    def test_role_has_tools(self) -> None:
        assert "market_ticker" in AGENT_ROLES["market_analyst"].allowed_tools
        assert "backtest_run" in AGENT_ROLES["strategy_architect"].allowed_tools
        assert "risk_check" in AGENT_ROLES["risk_guardian"].allowed_tools

    def test_get_role(self) -> None:
        role = get_role(AgentRole.MARKET_ANALYST)
        assert role.name == "Market Analyst"

    def test_role_definitions_are_frozen(self) -> None:
        role = get_role(AgentRole.STRATEGY_ARCHITECT)
        assert isinstance(role, RoleDefinition)
        assert role.name == "Strategy Architect"


# ---------------------------------------------------------------------------
# AgentRuntime tests (J09)
# ---------------------------------------------------------------------------


class TestLegacyAgentRuntime:
    """Tests for the legacy (pre-ReAct) agent runtime using JSON text parsing."""

    @pytest.fixture
    def catalog(self) -> ToolCatalog:
        cat = ToolCatalog()
        cat.register(_make_tool("market_ticker", "BTC/USDT: $67,000"))
        cat.register(_make_tool("risk_check", "ALLOWED"))
        return cat

    @pytest.fixture
    def context(self) -> ContextManager:
        return ContextManager()

    @pytest.fixture
    def prompt_ctx(self) -> AgentContext:
        return AgentContext(react_enabled=False)

    @pytest.mark.asyncio
    async def test_text_response(
        self, catalog: ToolCatalog, context: ContextManager, prompt_ctx: AgentContext
    ) -> None:
        llm = MockLLM([{"response": "Hello! How can I help?"}])
        runtime = LegacyAgentRuntime(llm, catalog, context, prompt_ctx)

        events = []
        async for event in runtime.process_message("hi"):
            events.append(event)

        types = [e.type for e in events]
        assert AgentStreamEventType.TEXT_DELTA in types
        assert AgentStreamEventType.DONE in types
        assert events[-1].type == AgentStreamEventType.DONE

        text_events = [e for e in events if e.type == AgentStreamEventType.TEXT_DELTA]
        assert "Hello" in text_events[0].data["text"]

    @pytest.mark.asyncio
    async def test_tool_call_then_response(
        self, catalog: ToolCatalog, context: ContextManager, prompt_ctx: AgentContext
    ) -> None:
        llm = MockLLM(
            [
                {
                    "response": "",
                    "tool_calls": [{"tool": "market_ticker", "arguments": {"symbol": "BTC/USDT"}}],
                },
                {"response": "BTC is at $67,000."},
            ]
        )
        runtime = LegacyAgentRuntime(llm, catalog, context, prompt_ctx)

        events = []
        async for event in runtime.process_message("What is BTC price?"):
            events.append(event)

        types = [e.type for e in events]
        assert AgentStreamEventType.TOOL_CALL in types
        assert AgentStreamEventType.TOOL_RESULT in types
        assert AgentStreamEventType.TEXT_DELTA in types
        assert AgentStreamEventType.DONE in types

    @pytest.mark.asyncio
    async def test_unknown_tool(
        self, catalog: ToolCatalog, context: ContextManager, prompt_ctx: AgentContext
    ) -> None:
        llm = MockLLM(
            [
                {
                    "response": "",
                    "tool_calls": [{"tool": "nonexistent", "arguments": {}}],
                },
                {"response": "Sorry, tool not found."},
            ]
        )
        runtime = LegacyAgentRuntime(llm, catalog, context, prompt_ctx)

        events = []
        async for event in runtime.process_message("do something"):
            events.append(event)

        result_events = [e for e in events if e.type == AgentStreamEventType.TOOL_RESULT]
        assert len(result_events) == 1
        assert "not found" in result_events[0].data.get("error", "")

    @pytest.mark.asyncio
    async def test_max_rounds_limit(
        self, catalog: ToolCatalog, context: ContextManager, prompt_ctx: AgentContext
    ) -> None:
        responses = [
            {"response": "", "tool_calls": [{"tool": "market_ticker", "arguments": {}}]}
            for _ in range(15)
        ]
        llm = MockLLM(responses)
        runtime = LegacyAgentRuntime(llm, catalog, context, prompt_ctx, max_tool_rounds=3)

        events = []
        async for event in runtime.process_message("loop"):
            events.append(event)

        text_events = [e for e in events if e.type == AgentStreamEventType.TEXT_DELTA]
        assert any("maximum" in e.data.get("text", "").lower() for e in text_events)

    @pytest.mark.asyncio
    async def test_blocked_tool(self, context: ContextManager, prompt_ctx: AgentContext) -> None:
        from pnlclaw_security.tool_policy import ToolPolicy, ToolPolicyEngine

        policy = ToolPolicyEngine([ToolPolicy(deny=["market_ticker"])])
        catalog = ToolCatalog(policy_engine=policy)
        catalog.register(_make_tool("market_ticker"))

        llm = MockLLM(
            [
                {"response": "", "tool_calls": [{"tool": "market_ticker", "arguments": {}}]},
                {"response": "Tool was blocked."},
            ]
        )
        runtime = LegacyAgentRuntime(llm, catalog, context, prompt_ctx)

        events = []
        async for event in runtime.process_message("get ticker"):
            events.append(event)

        result_events = [e for e in events if e.type == AgentStreamEventType.TOOL_RESULT]
        assert len(result_events) == 1
        assert "blocked" in result_events[0].data.get("error", "").lower()


class TestAgentRuntimeAlias:
    """Verify AgentRuntime alias points to ReActAgentRuntime."""

    def test_alias_is_react(self) -> None:
        from pnlclaw_agent.react import ReActAgentRuntime
        assert AgentRuntime is ReActAgentRuntime
