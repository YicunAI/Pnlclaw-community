"""ReAct (Reasoning + Acting) agent runtime.

Implements the Observe → Think → Act → Reflect → Answer loop with
native function calling, structured logging, error recovery, and
tool-loop detection.

v0.1.2 enhancements:
- Per-round tool result truncation in the conversation list
- Dynamic conversation trimming when approaching context limits
- Automatic recovery from LLMContextLengthError
- Token-aware proactive compaction using prompt_tokens feedback
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from pnlclaw_agent.context.manager import ContextManager, count_tokens
from pnlclaw_agent.prompt_builder import AgentContext, build_system_prompt
from pnlclaw_agent.runtime import LLMProviderProtocol
from pnlclaw_agent.tool_catalog import ToolCatalog
from pnlclaw_llm.schemas import ToolCallResult
from pnlclaw_types.agent import AgentStreamEvent, AgentStreamEventType

logger = logging.getLogger(__name__)

_MAX_CONSECUTIVE_NO_PROGRESS = 3
_MAX_SAME_CALL_REPEATS = 3
_MAX_TOOL_RESULT_CHARS = 6000
_TOKEN_WARN_RATIO = 0.75
_DEFAULT_CTX_WINDOW = 64_000


def _truncate_tool_output(content: str, max_chars: int = _MAX_TOOL_RESULT_CHARS) -> str:
    """Truncate a tool result for the conversation list.

    Keeps first and last portions, inserting a marker in the middle.
    """
    if len(content) <= max_chars:
        return content
    half = (max_chars - 60) // 2
    orig_tokens = count_tokens(content)
    return content[:half] + f"\n[...truncated {orig_tokens} tokens to fit context...]\n" + content[-half:]


class ReActAgentRuntime:
    """ReAct decision loop: Observe → Think → Act → Reflect → Answer.

    Prefers native ``chat_with_tools()`` for tool invocation; falls back
    to JSON text parsing when the LLM provider does not support native
    function calling.
    """

    def __init__(
        self,
        llm: LLMProviderProtocol,
        tool_catalog: ToolCatalog,
        context_manager: ContextManager,
        prompt_context: AgentContext,
        max_tool_rounds: int | None = None,
        on_checkpoint: Any | None = None,
    ) -> None:
        self._llm: LLMProviderProtocol = llm
        self._catalog = tool_catalog
        self._context = context_manager
        self._prompt_context = prompt_context
        self._max_tool_rounds = max_tool_rounds or prompt_context.max_tool_rounds
        self._on_checkpoint = on_checkpoint

    async def process_message(self, user_message: str) -> AsyncIterator[AgentStreamEvent]:
        """Process a user message through the ReAct loop.

        Yields ``AgentStreamEvent`` objects in order:
        THINKING → TOOL_CALL → TOOL_RESULT → REFLECTION → ... → TEXT_DELTA → DONE

        Maintains an OpenAI-compatible conversation list with proper
        ``tool_calls`` and ``tool_call_id`` fields for multi-turn function
        calling.  Previous conversation turns are loaded from the
        ``ContextManager`` so the LLM has full multi-turn context.

        Actively manages the conversation size to stay within the model's
        context window by truncating tool results and compacting old rounds.
        """
        self._context.add_message("user", user_message)

        system_prompt = build_system_prompt(self._prompt_context)
        conversation: list[dict[str, Any]] = self._build_llm_messages(system_prompt)

        call_history: list[str] = []
        no_progress_count = 0
        collected_tool_results: list[dict[str, Any]] = []
        last_prompt_tokens = 0

        for round_num in range(1, self._max_tool_rounds + 1):
            round_start = time.monotonic()

            yield _event(
                AgentStreamEventType.THINKING,
                {
                    "content": f"Round {round_num}: analyzing request and deciding next action...",
                    "round": round_num,
                },
            )

            # Proactive trim if approaching context limit
            if last_prompt_tokens > 0:
                warn_threshold = int(_DEFAULT_CTX_WINDOW * _TOKEN_WARN_RATIO)
                if last_prompt_tokens > warn_threshold:
                    conversation = self._compact_conversation(conversation)
                    logger.info(
                        "react_proactive_trim",
                        extra={
                            "prompt_tokens": last_prompt_tokens,
                            "threshold": warn_threshold,
                            "msgs_after": len(conversation),
                        },
                    )

            # --- Act: call LLM with tools, with context-overflow recovery ---
            tool_result: ToolCallResult | None = None
            for attempt in range(3):
                try:
                    tool_result = await self._call_llm_with_tools(conversation)
                    break
                except Exception as exc:
                    from pnlclaw_llm.base import LLMContextLengthError

                    if isinstance(exc, LLMContextLengthError):
                        logger.warning(
                            "react_context_overflow",
                            extra={
                                "round": round_num,
                                "attempt": attempt + 1,
                                "msgs": len(conversation),
                            },
                        )
                        conversation = self._compact_conversation(conversation, aggressive=True)
                        continue
                    if attempt == 0:
                        logger.error(
                            "react_llm_error",
                            extra={
                                "round": round_num,
                                "error": str(exc),
                            },
                            exc_info=True,
                        )
                        continue
                    logger.error(
                        "react_llm_retry_failed",
                        extra={
                            "round": round_num,
                            "error": str(exc),
                        },
                        exc_info=True,
                    )
                    yield _event(
                        AgentStreamEventType.TEXT_DELTA,
                        {
                            "text": self._format_partial_answer(collected_tool_results, str(exc)),
                        },
                    )
                    yield _event(AgentStreamEventType.DONE, {})
                    return

            if tool_result is None:
                yield _event(
                    AgentStreamEventType.TEXT_DELTA,
                    {
                        "text": self._format_partial_answer(
                            collected_tool_results,
                            "Unable to get response from LLM after context trimming.",
                        ),
                    },
                )
                yield _event(AgentStreamEventType.DONE, {})
                return

            last_prompt_tokens = tool_result.usage.prompt_tokens

            if tool_result.tool_calls:
                conversation.append(
                    {
                        "role": "assistant",
                        "content": tool_result.text or None,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                                },
                            }
                            for tc in tool_result.tool_calls
                        ],
                    }
                )

                for tc in tool_result.tool_calls:
                    call_key = f"{tc.name}:{json.dumps(tc.arguments, sort_keys=True)}"

                    recent = call_history[-(_MAX_SAME_CALL_REPEATS - 1) :]
                    if recent.count(call_key) >= _MAX_SAME_CALL_REPEATS - 1:
                        logger.warning(
                            "react_loop_detected",
                            extra={
                                "tool": tc.name,
                                "repeat_count": _MAX_SAME_CALL_REPEATS,
                            },
                        )
                        yield _event(
                            AgentStreamEventType.TEXT_DELTA,
                            {
                                "text": f"Tool loop detected: {tc.name} called {_MAX_SAME_CALL_REPEATS} times with same arguments. Stopping.",
                            },
                        )
                        yield _event(AgentStreamEventType.DONE, {})
                        return
                    call_history.append(call_key)

                    yield _event(
                        AgentStreamEventType.TOOL_CALL,
                        {
                            "tool": tc.name,
                            "arguments": tc.arguments,
                        },
                    )

                    tool_output = await self._execute_tool(tc.name, tc.arguments)
                    collected_tool_results.append({"tool": tc.name, **tool_output})

                    yield _event(
                        AgentStreamEventType.TOOL_RESULT,
                        {
                            "tool": tc.name,
                            **tool_output,
                        },
                    )

                    truncated_content = _truncate_tool_output(
                        tool_output.get("output", "") or tool_output.get("error", "")
                    )
                    conversation.append(
                        {
                            "role": "tool",
                            "content": truncated_content,
                            "tool_call_id": tc.id,
                        }
                    )

                    if self._on_checkpoint:
                        try:
                            self._on_checkpoint(
                                {
                                    "round": round_num,
                                    "tool": tc.name,
                                    "collected_count": len(collected_tool_results),
                                }
                            )
                        except Exception:
                            pass

                no_progress_count = 0
            else:
                no_progress_count += 1

            elapsed_ms = int((time.monotonic() - round_start) * 1000)
            logger.info(
                "react_round",
                extra={
                    "round": round_num,
                    "action": "act" if tool_result.tool_calls else "reflect",
                    "tool": tool_result.tool_calls[0].name if tool_result.tool_calls else None,
                    "tokens_used": tool_result.usage.total_tokens,
                    "prompt_tokens": last_prompt_tokens,
                    "elapsed_ms": elapsed_ms,
                },
            )

            if not tool_result.tool_calls:
                text = tool_result.text or ""
                if text:
                    yield _event(
                        AgentStreamEventType.REFLECTION,
                        {
                            "content": "Information sufficient, generating final answer.",
                            "round": round_num,
                        },
                    )
                    text = self._apply_hallucination_check(text, collected_tool_results)
                    self._context.add_message("assistant", text)
                    yield _event(AgentStreamEventType.TEXT_DELTA, {"text": text})
                    yield _event(AgentStreamEventType.DONE, {})
                    return

            yield _event(
                AgentStreamEventType.REFLECTION,
                {
                    "content": f"Round {round_num} complete. Evaluating if more data is needed...",
                    "round": round_num,
                },
            )

            if no_progress_count >= _MAX_CONSECUTIVE_NO_PROGRESS:
                logger.warning(
                    "react_no_progress",
                    extra={
                        "rounds_without_progress": no_progress_count,
                    },
                )
                yield _event(
                    AgentStreamEventType.TEXT_DELTA,
                    {
                        "text": self._format_partial_answer(
                            collected_tool_results,
                            "Reached maximum rounds without progress.",
                        ),
                    },
                )
                yield _event(AgentStreamEventType.DONE, {})
                return

        warning = f"Reached maximum tool calling rounds ({self._max_tool_rounds}). Stopping to prevent infinite loops."
        self._context.add_message("assistant", warning)
        yield _event(AgentStreamEventType.TEXT_DELTA, {"text": warning})
        yield _event(AgentStreamEventType.DONE, {})

    # -- Conversation management ------------------------------------------------

    @staticmethod
    def _compact_conversation(
        conversation: list[dict[str, Any]],
        *,
        aggressive: bool = False,
    ) -> list[dict[str, Any]]:
        """Trim the conversation to stay within context limits.

        Keeps the system prompt, user message, and the most recent tool
        rounds.  Older tool results are summarized into a compact
        ``[summary]`` message.

        When ``aggressive=True`` (e.g. after a context-overflow error),
        keeps only the last 3 tool rounds and truncates all tool results
        to 1500 chars.
        """
        if len(conversation) <= 6:
            return conversation

        keep_recent = 6 if aggressive else 12
        max_result_chars = 1500 if aggressive else _MAX_TOOL_RESULT_CHARS

        # Always keep: system (index 0) + first user message
        head: list[dict[str, Any]] = []
        body: list[dict[str, Any]] = []
        for msg in conversation:
            if msg.get("role") in ("system",) and not body:
                head.append(msg)
            else:
                body.append(msg)

        # Identify the first user message in body
        user_msg_idx = -1
        for i, msg in enumerate(body):
            if msg.get("role") == "user":
                user_msg_idx = i
                break

        if user_msg_idx >= 0:
            head.append(body[user_msg_idx])
            rest = body[:user_msg_idx] + body[user_msg_idx + 1 :]
        else:
            rest = body

        if len(rest) <= keep_recent:
            return head + rest

        # Summarize old rounds, keep recent ones
        old = rest[:-keep_recent]
        recent = rest[-keep_recent:]

        tool_names: list[str] = []
        for msg in old:
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    name = tc.get("function", {}).get("name", "")
                    if name:
                        tool_names.append(name)

        summary = (
            f"[Context compacted: {len(old)} earlier messages removed. "
            f"Tools called: {', '.join(tool_names[:10]) or 'none'}]"
        )
        compacted = head + [{"role": "system", "content": summary}]

        for msg in recent:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if len(content) > max_result_chars:
                    half = max_result_chars // 2
                    msg = {
                        **msg,
                        "content": content[:half] + "\n[...truncated...]\n" + content[-half:],
                    }
            compacted.append(msg)

        logger.info(
            "react_compact",
            extra={
                "removed": len(old),
                "kept": len(recent),
                "aggressive": aggressive,
            },
        )
        return compacted

    # -- LLM interaction -------------------------------------------------------

    async def _call_llm_with_tools(
        self,
        messages: list[dict[str, str]],
    ) -> ToolCallResult:
        """Try native chat_with_tools, fall back to JSON text parsing."""
        tool_defs = self._catalog.get_tool_definitions()

        if hasattr(self._llm, "chat_with_tools"):
            try:
                return await self._llm.chat_with_tools(messages, tools=tool_defs)
            except NotImplementedError:
                pass

        # Fallback: use chat() and parse JSON
        raw_text = await self._llm.chat(messages)
        return self._parse_text_as_tool_result(raw_text)

    @staticmethod
    def _parse_text_as_tool_result(raw_text: str) -> ToolCallResult:
        """Parse raw LLM text into a ToolCallResult (JSON fallback)."""
        from pnlclaw_llm.schemas import ToolCall
        from pnlclaw_llm.schemas import ToolCallResult as TCR

        stripped = raw_text.strip()
        if not stripped:
            return TCR(text="")

        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    raw_calls = parsed.get("tool_calls", [])
                    if isinstance(raw_calls, list) and raw_calls:
                        calls = []
                        for i, tc in enumerate(raw_calls):
                            if isinstance(tc, dict):
                                calls.append(
                                    ToolCall(
                                        id=f"json_call_{i}",
                                        name=tc.get("tool", tc.get("name", "")),
                                        arguments=tc.get("arguments", {}),
                                    )
                                )
                        text = parsed.get("response", "")
                        return TCR(tool_calls=calls, text=text or None)
                    text = parsed.get("response", "")
                    if text:
                        return TCR(text=text)
            except (json.JSONDecodeError, ValueError):
                pass

        return TCR(text=stripped)

    # -- Tool execution --------------------------------------------------------

    async def _execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool with security checks and error handling.

        Prefers ``async_execute`` when the tool provides one (e.g. for
        REST-backed data fetchers), falling back to ``execute`` via
        ``asyncio.to_thread`` for sync tools.
        """
        if not self._catalog.is_tool_allowed(tool_name):
            error_text = f"Tool '{tool_name}' is blocked by security policy."
            return {"output": "", "error": error_text}

        tool = self._catalog.get(tool_name)
        if tool is None:
            error_text = f"Tool '{tool_name}' not found."
            return {"output": "", "error": error_text}

        try:
            result = None
            if hasattr(tool, "async_execute"):
                result = await tool.async_execute(arguments)
            if result is None:
                result = await asyncio.to_thread(tool.execute, arguments)
            return {
                "output": result.output,
                "error": result.error,
            }
        except Exception as exc:
            logger.error(
                "react_tool_error",
                extra={
                    "tool": tool_name,
                    "error": str(exc),
                },
                exc_info=True,
            )
            return {"output": "", "error": f"Tool execution error: {exc}"}

    # -- Hallucination check ---------------------------------------------------

    def _apply_hallucination_check(
        self,
        text: str,
        tool_results: list[dict[str, Any]],
    ) -> str:
        """Run hallucination detection on final answer if enabled."""
        if not self._prompt_context.hallucination_check:
            return text
        try:
            from pnlclaw_security.guardrails.hallucination import HallucinationDetector

            detector = HallucinationDetector()
            text, _scan_result = detector.scan_output(text, tool_results=tool_results)
        except ImportError:
            logger.debug("security-gateway not available, skipping hallucination check")
        except Exception as exc:
            logger.warning("hallucination_check_failed", extra={"error": str(exc)})
        return text

    # -- Helpers ---------------------------------------------------------------

    def _build_llm_messages(self, system_prompt: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        for msg in self._context.get_messages():
            messages.append({"role": msg.role, "content": msg.content})
        return messages

    @staticmethod
    def _format_partial_answer(
        tool_results: list[dict[str, Any]],
        reason: str,
    ) -> str:
        """Build a partial answer from collected tool results when aborting."""
        parts = [reason]
        if tool_results:
            parts.append("\nAvailable data collected so far:")
            for tr in tool_results:
                output = tr.get("output", "")
                if output:
                    parts.append(f"- {tr.get('tool', 'unknown')}: {output[:200]}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helper — re-export from shared module for backward compatibility
# ---------------------------------------------------------------------------

from pnlclaw_agent.events import make_event as _event  # noqa: E402
