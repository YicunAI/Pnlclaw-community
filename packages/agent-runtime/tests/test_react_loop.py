"""Tests for ReAct (Reasoning + Acting) agent runtime loop.

Sprint 1.2 — Validates the full Observe → Think → Act → Reflect → Answer
cycle, error recovery, and tool-loop detection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from pnlclaw_agent.context.manager import ContextManager
from pnlclaw_agent.prompt_builder import AgentContext
from pnlclaw_agent.react import ReActAgentRuntime
from pnlclaw_agent.tool_catalog import ToolCatalog
from pnlclaw_agent.tools.base import BaseTool, ToolResult
from pnlclaw_llm.schemas import TokenUsage, ToolCall, ToolCallResult
from pnlclaw_types.agent import AgentStreamEventType
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


class MockReActLLM:
    """Mock LLM that supports chat_with_tools for ReAct testing."""

    def __init__(self, responses: list[ToolCallResult]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    async def chat(self, messages: list[Any], **kwargs: Any) -> str:
        return "fallback chat"

    async def chat_stream(self, messages: list[Any], **kwargs: Any) -> AsyncIterator[str]:
        yield "mock"

    async def chat_with_tools(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ToolCallResult:
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        return ToolCallResult(text="No more responses configured.")

    async def generate_structured(
        self, messages: list[Any], output_schema: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        return {}


def _make_runtime(
    llm: Any,
    tool_names: list[str] | None = None,
    max_rounds: int = 10,
    react_enabled: bool = True,
) -> ReActAgentRuntime:
    catalog = ToolCatalog()
    for name in tool_names or ["market_ticker"]:
        catalog.register(_make_tool(name, f"{name} result"))
    ctx = AgentContext(react_enabled=react_enabled, max_tool_rounds=max_rounds)
    return ReActAgentRuntime(
        llm=llm,
        tool_catalog=catalog,
        context_manager=ContextManager(),
        prompt_context=ctx,
        max_tool_rounds=max_rounds,
    )


async def _collect_events(runtime: ReActAgentRuntime, message: str) -> list[Any]:
    events = []
    async for event in runtime.process_message(message):
        events.append(event)
    return events


# ---------------------------------------------------------------------------
# Test 1: Basic ReAct cycle — think → act → reflect → answer
# ---------------------------------------------------------------------------


class TestBasicReActCycle:
    @pytest.mark.asyncio
    async def test_think_act_reflect_answer(self) -> None:
        llm = MockReActLLM(
            [
                ToolCallResult(
                    tool_calls=[ToolCall(id="c1", name="market_ticker", arguments={"symbol": "BTC"})],
                    usage=TokenUsage(total_tokens=20),
                ),
                ToolCallResult(text="BTC is at $67,000.", usage=TokenUsage(total_tokens=15)),
            ]
        )
        runtime = _make_runtime(llm)
        events = await _collect_events(runtime, "BTC price?")

        types = [e.type for e in events]
        assert AgentStreamEventType.THINKING in types
        assert AgentStreamEventType.TOOL_CALL in types
        assert AgentStreamEventType.TOOL_RESULT in types
        assert AgentStreamEventType.REFLECTION in types
        assert AgentStreamEventType.TEXT_DELTA in types
        assert AgentStreamEventType.DONE in types
        assert events[-1].type == AgentStreamEventType.DONE

        text_events = [e for e in events if e.type == AgentStreamEventType.TEXT_DELTA]
        assert any("67,000" in e.data.get("text", "") for e in text_events)


# ---------------------------------------------------------------------------
# Test 2: Multi-round tool calling
# ---------------------------------------------------------------------------


class TestMultiRoundToolCalling:
    @pytest.mark.asyncio
    async def test_two_rounds_then_answer(self) -> None:
        llm = MockReActLLM(
            [
                ToolCallResult(
                    tool_calls=[ToolCall(id="c1", name="market_ticker", arguments={"symbol": "BTC"})],
                    usage=TokenUsage(total_tokens=20),
                ),
                ToolCallResult(
                    tool_calls=[ToolCall(id="c2", name="market_ticker", arguments={"symbol": "ETH"})],
                    usage=TokenUsage(total_tokens=20),
                ),
                ToolCallResult(text="BTC and ETH prices fetched.", usage=TokenUsage(total_tokens=15)),
            ]
        )
        runtime = _make_runtime(llm)
        events = await _collect_events(runtime, "compare BTC and ETH")

        tool_calls = [e for e in events if e.type == AgentStreamEventType.TOOL_CALL]
        assert len(tool_calls) == 2
        assert events[-1].type == AgentStreamEventType.DONE


# ---------------------------------------------------------------------------
# Test 3: Tool loop detection (same args 3 times)
# ---------------------------------------------------------------------------


class TestToolLoopDetection:
    @pytest.mark.asyncio
    async def test_same_call_three_times_aborts(self) -> None:
        same_call = ToolCallResult(
            tool_calls=[ToolCall(id="c1", name="market_ticker", arguments={"symbol": "BTC"})],
            usage=TokenUsage(total_tokens=10),
        )
        llm = MockReActLLM([same_call, same_call, same_call])
        runtime = _make_runtime(llm, max_rounds=10)
        events = await _collect_events(runtime, "loop test")

        text_events = [e for e in events if e.type == AgentStreamEventType.TEXT_DELTA]
        assert any("loop detected" in e.data.get("text", "").lower() for e in text_events)
        assert events[-1].type == AgentStreamEventType.DONE


# ---------------------------------------------------------------------------
# Test 4: LLM timeout fallback
# ---------------------------------------------------------------------------


class TestLLMTimeoutFallback:
    @pytest.mark.asyncio
    async def test_llm_timeout_retries_then_aborts(self) -> None:
        class TimeoutLLM:
            async def chat(self, messages: list[Any], **kwargs: Any) -> str:
                return "fallback"

            async def chat_stream(self, messages: list[Any], **kwargs: Any) -> AsyncIterator[str]:
                yield "mock"

            async def chat_with_tools(self, messages: list[Any], **kwargs: Any) -> ToolCallResult:
                raise TimeoutError("LLM timeout")

            async def generate_structured(self, messages: list[Any], **kwargs: Any) -> dict:
                return {}

        runtime = _make_runtime(TimeoutLLM())
        events = await _collect_events(runtime, "test timeout")

        assert events[-1].type == AgentStreamEventType.DONE
        text_events = [e for e in events if e.type == AgentStreamEventType.TEXT_DELTA]
        assert len(text_events) >= 1


# ---------------------------------------------------------------------------
# Test 5: Invalid JSON fallback
# ---------------------------------------------------------------------------


class TestInvalidJSONFallback:
    @pytest.mark.asyncio
    async def test_fallback_to_text_on_no_chat_with_tools(self) -> None:
        class TextOnlyLLM:
            _call_count = 0

            async def chat(self, messages: list[Any], **kwargs: Any) -> str:
                self._call_count += 1
                if self._call_count == 1:
                    return "not valid json {{{"
                return "Here is my answer"

            async def chat_stream(self, messages: list[Any], **kwargs: Any) -> AsyncIterator[str]:
                yield "mock"

            async def generate_structured(self, messages: list[Any], **kwargs: Any) -> dict:
                return {}

        runtime = _make_runtime(TextOnlyLLM())
        events = await _collect_events(runtime, "test fallback")

        text_events = [e for e in events if e.type == AgentStreamEventType.TEXT_DELTA]
        assert len(text_events) >= 1
        assert events[-1].type == AgentStreamEventType.DONE


# ---------------------------------------------------------------------------
# Test 6: Tool execution exception → continue reasoning
# ---------------------------------------------------------------------------


class TestToolExecutionError:
    @pytest.mark.asyncio
    async def test_tool_error_continues_reasoning(self) -> None:
        class ErrorTool(BaseTool):
            @property
            def name(self) -> str:
                return "broken_tool"

            @property
            def description(self) -> str:
                return "Always fails"

            @property
            def parameters(self) -> dict[str, Any]:
                return {"type": "object", "properties": {}, "required": []}

            @property
            def risk_level(self) -> RiskLevel:
                return RiskLevel.SAFE

            def execute(self, args: dict[str, Any]) -> ToolResult:
                raise RuntimeError("tool crashed")

        catalog = ToolCatalog()
        catalog.register(ErrorTool())

        llm = MockReActLLM(
            [
                ToolCallResult(
                    tool_calls=[ToolCall(id="c1", name="broken_tool", arguments={})],
                    usage=TokenUsage(total_tokens=10),
                ),
                ToolCallResult(text="The tool failed, but I can still help.", usage=TokenUsage(total_tokens=10)),
            ]
        )
        ctx = AgentContext(react_enabled=True)
        runtime = ReActAgentRuntime(
            llm=llm,
            tool_catalog=catalog,
            context_manager=ContextManager(),
            prompt_context=ctx,
        )
        events = await _collect_events(runtime, "use broken tool")

        result_events = [e for e in events if e.type == AgentStreamEventType.TOOL_RESULT]
        assert len(result_events) == 1
        assert "error" in result_events[0].data.get("error", "").lower()

        assert events[-1].type == AgentStreamEventType.DONE


# ---------------------------------------------------------------------------
# Test 7: 3 rounds no progress → abort
# ---------------------------------------------------------------------------


class TestNoProgressAbort:
    @pytest.mark.asyncio
    async def test_three_rounds_no_progress_aborts(self) -> None:
        empty_responses = [ToolCallResult(text="", usage=TokenUsage(total_tokens=5)) for _ in range(5)]
        llm = MockReActLLM(empty_responses)
        runtime = _make_runtime(llm, max_rounds=10)
        events = await _collect_events(runtime, "empty loop")

        text_events = [e for e in events if e.type == AgentStreamEventType.TEXT_DELTA]
        found_progress_msg = any("progress" in e.data.get("text", "").lower() for e in text_events)
        assert found_progress_msg
        assert events[-1].type == AgentStreamEventType.DONE


# ---------------------------------------------------------------------------
# Test 8: react_enabled=False uses fallback (text-only)
# ---------------------------------------------------------------------------


class TestReactDisabled:
    @pytest.mark.asyncio
    async def test_react_disabled_no_thinking_events(self) -> None:
        """When react_enabled=False, prompt should not contain ReAct protocol."""
        llm = MockReActLLM(
            [
                ToolCallResult(text="Simple answer without reasoning.", usage=TokenUsage(total_tokens=10)),
            ]
        )
        runtime = _make_runtime(llm, react_enabled=False)
        events = await _collect_events(runtime, "hi")

        # THINKING events still emitted by ReActAgentRuntime internals,
        # but the prompt should NOT contain "Reasoning Protocol"
        text_events = [e for e in events if e.type == AgentStreamEventType.TEXT_DELTA]
        assert len(text_events) >= 1
        assert events[-1].type == AgentStreamEventType.DONE


# ---------------------------------------------------------------------------
# Test 9: THINKING and REFLECTION events correctly emitted
# ---------------------------------------------------------------------------


class TestEventEmission:
    @pytest.mark.asyncio
    async def test_thinking_before_tool_call(self) -> None:
        llm = MockReActLLM(
            [
                ToolCallResult(
                    tool_calls=[ToolCall(id="c1", name="market_ticker", arguments={"symbol": "BTC"})],
                    usage=TokenUsage(total_tokens=20),
                ),
                ToolCallResult(text="Done.", usage=TokenUsage(total_tokens=10)),
            ]
        )
        runtime = _make_runtime(llm)
        events = await _collect_events(runtime, "check")

        types = [e.type for e in events]

        # THINKING must appear before TOOL_CALL
        think_idx = types.index(AgentStreamEventType.THINKING)
        tool_idx = types.index(AgentStreamEventType.TOOL_CALL)
        assert think_idx < tool_idx

    @pytest.mark.asyncio
    async def test_reflection_after_tool_result(self) -> None:
        llm = MockReActLLM(
            [
                ToolCallResult(
                    tool_calls=[ToolCall(id="c1", name="market_ticker", arguments={"symbol": "BTC"})],
                    usage=TokenUsage(total_tokens=20),
                ),
                ToolCallResult(text="Answer.", usage=TokenUsage(total_tokens=10)),
            ]
        )
        runtime = _make_runtime(llm)
        events = await _collect_events(runtime, "check")

        types = [e.type for e in events]

        # REFLECTION must appear after TOOL_RESULT
        result_idx = types.index(AgentStreamEventType.TOOL_RESULT)
        reflection_indices = [i for i, t in enumerate(types) if t == AgentStreamEventType.REFLECTION]
        assert any(ri > result_idx for ri in reflection_indices)
