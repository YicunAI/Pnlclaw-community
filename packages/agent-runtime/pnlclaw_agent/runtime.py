"""Agent runtime — core LLM conversation loop with tool calling.

The runtime orchestrates: user message → LLM → tool calls → results → reply.
LLM is injected via Protocol (no direct import of pnlclaw_llm).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from pnlclaw_agent.context.manager import ContextManager
from pnlclaw_agent.prompt_builder import AgentContext, build_system_prompt
from pnlclaw_agent.tool_catalog import ToolCatalog
from pnlclaw_types.agent import AgentStreamEvent, AgentStreamEventType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Provider Protocol (structural typing — no import of pnlclaw_llm)
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """Protocol matching the LLMProvider ABC from pnlclaw_llm."""

    async def chat(self, messages: list[Any], **kwargs: Any) -> str: ...

    async def chat_stream(self, messages: list[Any], **kwargs: Any) -> AsyncIterator[str]: ...

    async def generate_structured(
        self, messages: list[Any], output_schema: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]: ...

    async def chat_with_tools(
        self, messages: list[Any], tools: list[dict[str, Any]] | None = None, **kwargs: Any
    ) -> Any: ...


# ---------------------------------------------------------------------------
# AgentRuntime
# ---------------------------------------------------------------------------


class AgentRuntimeError(Exception):
    """Raised when the agent runtime encounters an unrecoverable error."""


class LegacyAgentRuntime:
    """Legacy agent conversation loop (pre-ReAct).

    Uses plain ``chat`` for LLM interaction to maximize provider
    compatibility.  When the model's response is valid JSON containing
    ``tool_calls``, those tools are executed and results fed back.
    Otherwise the text is returned directly.

    .. deprecated:: 0.1.1
        Use ``ReActAgentRuntime`` (aliased as ``AgentRuntime``) instead.
    """

    def __init__(
        self,
        llm: LLMProviderProtocol,
        tool_catalog: ToolCatalog,
        context_manager: ContextManager,
        prompt_context: AgentContext,
        max_tool_rounds: int = 10,
    ) -> None:
        self._llm = llm
        self._catalog = tool_catalog
        self._context = context_manager
        self._prompt_context = prompt_context
        self._max_tool_rounds = max_tool_rounds

    async def process_message(self, user_message: str) -> AsyncIterator[AgentStreamEvent]:
        """Process a user message through the LLM with optional tool calling.

        Yields AgentStreamEvent objects (TEXT_DELTA, TOOL_CALL, TOOL_RESULT, DONE).
        """
        self._context.add_message("user", user_message)

        for _round_num in range(self._max_tool_rounds):
            system_prompt = build_system_prompt(self._prompt_context)
            llm_messages = self._build_llm_messages(system_prompt)

            try:
                raw_text = await self._llm.chat(llm_messages)
            except Exception as exc:
                yield _event(
                    AgentStreamEventType.TEXT_DELTA,
                    {"text": f"LLM error: {exc}"},
                )
                yield _event(AgentStreamEventType.DONE, {})
                return

            # Try to interpret as structured JSON (for tool calling)
            tool_calls, text_response = self._parse_response(raw_text)

            if not tool_calls:
                if text_response:
                    self._context.add_message("assistant", text_response)
                    yield _event(
                        AgentStreamEventType.TEXT_DELTA,
                        {"text": text_response},
                    )
                yield _event(AgentStreamEventType.DONE, {})
                return

            # Process tool calls
            for tc in tool_calls:
                tool_name = tc.get("tool", "")
                tool_args = tc.get("arguments", {})

                yield _event(
                    AgentStreamEventType.TOOL_CALL,
                    {"tool": tool_name, "arguments": tool_args},
                )

                if not self._catalog.is_tool_allowed(tool_name):
                    error_text = f"Tool '{tool_name}' is blocked by security policy."
                    self._context.add_message("tool", error_text, {"tool_name": tool_name})
                    yield _event(
                        AgentStreamEventType.TOOL_RESULT,
                        {"tool": tool_name, "output": "", "error": error_text},
                    )
                    continue

                tool = self._catalog.get(tool_name)
                if tool is None:
                    error_text = f"Tool '{tool_name}' not found."
                    self._context.add_message("tool", error_text, {"tool_name": tool_name})
                    yield _event(
                        AgentStreamEventType.TOOL_RESULT,
                        {"tool": tool_name, "output": "", "error": error_text},
                    )
                    continue

                try:
                    result = None
                    if hasattr(tool, "async_execute"):
                        result = await tool.async_execute(tool_args)
                    if result is None:
                        result = await asyncio.to_thread(tool.execute, tool_args)
                except Exception as exc:
                    error_text = f"Tool execution error: {exc}"
                    self._context.add_message("tool", error_text, {"tool_name": tool_name})
                    yield _event(
                        AgentStreamEventType.TOOL_RESULT,
                        {"tool": tool_name, "output": "", "error": error_text},
                    )
                    continue

                result_text = result.output if not result.error else f"Error: {result.error}\n{result.output}"
                self._context.add_message("tool", result_text, {"tool_name": tool_name})
                yield _event(
                    AgentStreamEventType.TOOL_RESULT,
                    {"tool": tool_name, "output": result.output, "error": result.error},
                )

            call_summary = ", ".join(tc.get("tool", "") for tc in tool_calls)
            self._context.add_message(
                "assistant",
                f"[Called tools: {call_summary}]",
                {"tool_calls": tool_calls},
            )

        warning = f"Reached maximum tool calling rounds ({self._max_tool_rounds}). Stopping to prevent infinite loops."
        self._context.add_message("assistant", warning)
        yield _event(AgentStreamEventType.TEXT_DELTA, {"text": warning})
        yield _event(AgentStreamEventType.DONE, {})

    # -- internal ------------------------------------------------------------

    @staticmethod
    def _parse_response(raw_text: str) -> tuple[list[dict[str, Any]], str]:
        """Parse LLM text into (tool_calls, text_response).

        If the text is valid JSON with a ``tool_calls`` list, those are
        extracted.  Otherwise the entire text is treated as a direct reply.
        """
        stripped = raw_text.strip()
        if not stripped:
            return [], ""

        # Only try JSON parsing if it looks like JSON
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    tool_calls = parsed.get("tool_calls", [])
                    text = parsed.get("response", "")
                    if isinstance(tool_calls, list) and tool_calls:
                        return tool_calls, text
                    if text:
                        return [], text
            except (json.JSONDecodeError, ValueError):
                pass

        # Not JSON or no tool_calls — treat entire text as reply
        return [], stripped

    def _build_llm_messages(self, system_prompt: str) -> list[dict[str, str]]:
        """Build the message list for the LLM call."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        for msg in self._context.get_messages():
            messages.append({"role": msg.role, "content": msg.content})
        return messages


# ---------------------------------------------------------------------------
# Helper — re-export from shared module
# ---------------------------------------------------------------------------

from pnlclaw_agent.events import make_event as _event  # noqa: E402

# ---------------------------------------------------------------------------
# Backward-compatible alias: AgentRuntime → ReActAgentRuntime
# ---------------------------------------------------------------------------
from pnlclaw_agent.react import ReActAgentRuntime  # noqa: E402

AgentRuntime = ReActAgentRuntime
