"""Agent runtime — core LLM conversation loop with tool calling.

The runtime orchestrates: user message → LLM → tool calls → results → reply.
LLM is injected via Protocol (no direct import of pnlclaw_llm).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from pnlclaw_types.agent import AgentStreamEvent, AgentStreamEventType

from pnlclaw_agent.context.manager import ContextManager
from pnlclaw_agent.prompt_builder import AgentContext, build_system_prompt
from pnlclaw_agent.tool_catalog import ToolCatalog


# ---------------------------------------------------------------------------
# LLM Provider Protocol (structural typing — no import of pnlclaw_llm)
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """Protocol matching the LLMProvider ABC from pnlclaw_llm.

    Any object implementing these three async methods satisfies this
    protocol at runtime, without needing to import pnlclaw_llm.
    """

    async def chat(self, messages: list[Any], **kwargs: Any) -> str: ...

    async def chat_stream(
        self, messages: list[Any], **kwargs: Any
    ) -> AsyncIterator[str]: ...

    async def generate_structured(
        self, messages: list[Any], output_schema: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Response schema for structured LLM output
# ---------------------------------------------------------------------------

AGENT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "thinking": {
            "type": "string",
            "description": "Internal reasoning (not shown to user)",
        },
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["tool", "arguments"],
            },
            "description": "Tool calls to execute (empty if responding directly)",
        },
        "response": {
            "type": "string",
            "description": "Text response to the user (empty if calling tools)",
        },
    },
    "required": ["response"],
}


# ---------------------------------------------------------------------------
# AgentRuntime
# ---------------------------------------------------------------------------


class AgentRuntimeError(Exception):
    """Raised when the agent runtime encounters an unrecoverable error."""


class AgentRuntime:
    """Core agent conversation loop.

    Orchestrates: user message → build prompt → LLM → parse tool calls →
    execute tools → feed results back → continue or reply.

    Args:
        llm: LLM provider (injected, satisfies LLMProviderProtocol).
        tool_catalog: Registry of available tools.
        context_manager: Conversation history and token management.
        prompt_context: Context for building the system prompt.
        max_tool_rounds: Maximum number of tool-calling rounds per
            user message (default 10).
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

    async def process_message(
        self, user_message: str
    ) -> AsyncIterator[AgentStreamEvent]:
        """Process a user message through the LLM with tool calling.

        Yields AgentStreamEvent objects:
        - TOOL_CALL: when the LLM requests a tool
        - TOOL_RESULT: after tool execution
        - TEXT_DELTA: text response from the LLM
        - DONE: conversation turn complete

        Args:
            user_message: The user's input text.

        Yields:
            AgentStreamEvent instances.
        """
        now_ms = int(time.time() * 1000)

        # Add user message to context
        self._context.add_message("user", user_message)

        for round_num in range(self._max_tool_rounds):
            # Build system prompt
            system_prompt = build_system_prompt(self._prompt_context)

            # Construct LLM messages
            llm_messages = self._build_llm_messages(system_prompt)

            # Call LLM for structured response
            try:
                response = await self._llm.generate_structured(
                    llm_messages, AGENT_RESPONSE_SCHEMA
                )
            except Exception as exc:
                yield _event(
                    AgentStreamEventType.TEXT_DELTA,
                    {"text": f"LLM error: {exc}"},
                )
                yield _event(AgentStreamEventType.DONE, {})
                return

            # Extract tool calls and response
            tool_calls = response.get("tool_calls", [])
            text_response = response.get("response", "")

            if not tool_calls:
                # No tool calls — return text response
                if text_response:
                    self._context.add_message("assistant", text_response)
                    yield _event(
                        AgentStreamEventType.TEXT_DELTA,
                        {"text": text_response},
                    )
                yield _event(AgentStreamEventType.DONE, {})
                return

            # Process tool calls
            has_results = False
            for tc in tool_calls:
                tool_name = tc.get("tool", "")
                tool_args = tc.get("arguments", {})

                yield _event(
                    AgentStreamEventType.TOOL_CALL,
                    {"tool": tool_name, "arguments": tool_args},
                )

                # Check policy
                if not self._catalog.is_tool_allowed(tool_name):
                    error_text = f"Tool '{tool_name}' is blocked by security policy."
                    self._context.add_message("tool", error_text, {"tool_name": tool_name})
                    yield _event(
                        AgentStreamEventType.TOOL_RESULT,
                        {"tool": tool_name, "output": "", "error": error_text},
                    )
                    continue

                # Get tool
                tool = self._catalog.get(tool_name)
                if tool is None:
                    error_text = f"Tool '{tool_name}' not found."
                    self._context.add_message("tool", error_text, {"tool_name": tool_name})
                    yield _event(
                        AgentStreamEventType.TOOL_RESULT,
                        {"tool": tool_name, "output": "", "error": error_text},
                    )
                    continue

                # Execute tool in thread pool (tools are sync)
                try:
                    result = await asyncio.to_thread(tool.execute, tool_args)
                except Exception as exc:
                    error_text = f"Tool execution error: {exc}"
                    self._context.add_message("tool", error_text, {"tool_name": tool_name})
                    yield _event(
                        AgentStreamEventType.TOOL_RESULT,
                        {"tool": tool_name, "output": "", "error": error_text},
                    )
                    continue

                # Add result to context
                result_text = result.output if not result.error else f"Error: {result.error}\n{result.output}"
                self._context.add_message("tool", result_text, {"tool_name": tool_name})
                yield _event(
                    AgentStreamEventType.TOOL_RESULT,
                    {"tool": tool_name, "output": result.output, "error": result.error},
                )
                has_results = True

            # Add assistant message noting tool calls were made
            call_summary = ", ".join(tc.get("tool", "") for tc in tool_calls)
            self._context.add_message(
                "assistant",
                f"[Called tools: {call_summary}]",
                {"tool_calls": tool_calls},
            )

            # Continue loop for next LLM round with tool results

        # Exceeded max rounds
        warning = (
            f"Reached maximum tool calling rounds ({self._max_tool_rounds}). "
            f"Stopping to prevent infinite loops."
        )
        self._context.add_message("assistant", warning)
        yield _event(AgentStreamEventType.TEXT_DELTA, {"text": warning})
        yield _event(AgentStreamEventType.DONE, {})

    # -- internal ------------------------------------------------------------

    def _build_llm_messages(self, system_prompt: str) -> list[dict[str, str]]:
        """Build the message list for the LLM call."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        for msg in self._context.get_messages():
            messages.append({"role": msg.role, "content": msg.content})
        return messages


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _event(event_type: AgentStreamEventType, data: dict[str, Any]) -> AgentStreamEvent:
    """Create an AgentStreamEvent with current timestamp."""
    return AgentStreamEvent(
        type=event_type,
        data=data,
        timestamp=int(time.time() * 1000),
    )
