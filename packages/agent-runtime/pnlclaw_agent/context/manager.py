"""Context manager — maintains conversation history with token budgeting.

Tracks messages, estimates token usage, and auto-trims when the
conversation exceeds the configured budget.

v0.1.1 enhancements:
- tiktoken precise token counting (with graceful fallback)
- Auto-compaction trigger when tokens exceed threshold
- Market context injection into system prompt
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pnlclaw_types.agent import ChatMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token counting: tiktoken (precise) with fallback (4 chars/token)
# ---------------------------------------------------------------------------

_FALLBACK_CHARS_PER_TOKEN = 4

try:
    import tiktoken

    _encoder = tiktoken.encoding_for_model("gpt-4")

    def count_tokens(text: str) -> int:
        """Count tokens using tiktoken (precise)."""
        return max(1, len(_encoder.encode(text)))

    TIKTOKEN_AVAILABLE = True
except ImportError:

    def count_tokens(text: str) -> int:
        """Estimate tokens using 4 chars/token heuristic (fallback)."""
        return max(1, len(text) // _FALLBACK_CHARS_PER_TOKEN)

    TIKTOKEN_AVAILABLE = False


class ContextManager:
    """Manages agent conversation history with token budget enforcement.

    Uses tiktoken for precise token counting when available, falling
    back to the 4 chars/token heuristic otherwise. Automatically trims
    oldest non-system messages when the context exceeds ``max_tokens``
    or ``max_messages``. Supports auto-compaction and market context
    injection.
    """

    CHARS_PER_TOKEN = _FALLBACK_CHARS_PER_TOKEN

    def __init__(
        self,
        max_tokens: int = 200_000,
        max_messages: int = 100,
        compaction_threshold: float = 0.8,
        compactor: Any | None = None,
    ) -> None:
        self._messages: list[ChatMessage] = []
        self._max_tokens = max_tokens
        self._max_messages = max_messages
        self._compaction_threshold = compaction_threshold
        self._compactor = compactor
        self._compaction_in_progress = False

    # -- public API ----------------------------------------------------------

    def add_message(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a message and auto-trim if needed.

        Tool results are truncated before adding if they exceed 30% of
        the token budget.
        """
        if role == "tool":
            content = self.truncate_tool_result(content)

        msg = ChatMessage(
            role=role,
            content=content,
            timestamp=int(time.time() * 1000),
            metadata=metadata,
        )
        self._messages.append(msg)
        self._trim_if_needed()
        self._check_auto_compaction()

    def get_messages(self) -> list[ChatMessage]:
        """Return the current conversation history."""
        return list(self._messages)

    def estimate_tokens(self, text: str) -> int:
        """Count tokens for a text string.

        Uses tiktoken when available, falls back to 4 chars/token heuristic.
        """
        return count_tokens(text)

    def total_tokens(self) -> int:
        """Count total tokens across all messages."""
        return sum(self.estimate_tokens(m.content) for m in self._messages)

    def truncate_tool_result(
        self,
        content: str,
        budget_pct: float = 0.3,
    ) -> str:
        """Truncate a tool result if it exceeds a fraction of the token budget.

        Keeps the first and last portions of the content, inserting an
        ellipsis marker in the middle.

        Args:
            content: The tool result text.
            budget_pct: Maximum fraction of total token budget for a single
                tool result (default 0.3 = 30%).

        Returns:
            The original content, or truncated version.
        """
        max_chars = int(self._max_tokens * self.CHARS_PER_TOKEN * budget_pct)
        if len(content) <= max_chars:
            return content

        # Keep first half and last half
        keep_chars = max_chars - 80  # Reserve space for truncation marker
        half = keep_chars // 2
        original_tokens = self.estimate_tokens(content)
        kept_tokens = self.estimate_tokens(content[:half] + content[-half:])

        return (
            content[:half]
            + f"\n\n[... Truncated: {original_tokens} tokens → {kept_tokens} tokens ...]\n\n"
            + content[-half:]
        )

    def clear(self) -> None:
        """Clear all messages."""
        self._messages.clear()

    # -- serialization ---------------------------------------------------------

    def serialize(self) -> list[dict[str, Any]]:
        """Export messages for persistence (e.g. to SQLite via chat session repo)."""
        return [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
                "metadata": m.metadata,
            }
            for m in self._messages
        ]

    @classmethod
    def deserialize(
        cls,
        data: list[dict[str, Any]],
        *,
        max_tokens: int = 200_000,
        max_messages: int = 100,
    ) -> ContextManager:
        """Restore a ContextManager from serialized message data."""
        cm = cls(max_tokens=max_tokens, max_messages=max_messages)
        for item in data:
            msg = ChatMessage(
                role=item.get("role", "user"),
                content=item.get("content", ""),
                timestamp=item.get("timestamp") or int(time.time() * 1000),
                metadata=item.get("metadata"),
            )
            cm._messages.append(msg)
        cm._trim_if_needed()
        return cm

    @property
    def message_count(self) -> int:
        """Number of messages in history."""
        return len(self._messages)

    # -- market context injection ----------------------------------------------

    async def inject_market_context(
        self,
        symbols: list[str],
        prices: dict[str, float],
    ) -> None:
        """Inject current market prices into the system prompt context.

        Formats a concise market summary and adds it as a system message.
        Respects a 10% token budget limit for market context.
        """
        if not prices:
            return

        budget_limit = int(self._max_tokens * 0.10)
        lines = ["## Live Market Prices"]
        for sym in symbols:
            price = prices.get(sym)
            if price is not None:
                lines.append(f"- {sym}: ${price:,.2f}")

        summary = "\n".join(lines)

        if self.estimate_tokens(summary) > budget_limit:
            max_chars = budget_limit * _FALLBACK_CHARS_PER_TOKEN
            summary = summary[:max_chars] + "\n[... truncated ...]"

        # Replace existing market context or add new one
        for i, msg in enumerate(self._messages):
            if msg.role == "system" and msg.content.startswith("## Live Market Prices"):
                self._messages[i] = ChatMessage(
                    role="system",
                    content=summary,
                    timestamp=int(time.time() * 1000),
                )
                return

        self._messages.insert(
            0,
            ChatMessage(
                role="system",
                content=summary,
                timestamp=int(time.time() * 1000),
            ),
        )

    # -- auto compaction -------------------------------------------------------

    def _check_auto_compaction(self) -> None:
        """Trigger compaction if token usage exceeds threshold.

        Schedules ``_run_compaction()`` on the running event loop. If no
        loop is available (sync context), the compaction is silently
        skipped — callers can trigger it explicitly via ``compact()``.
        """
        if self._compaction_in_progress or self._compactor is None:
            return

        current = self.total_tokens()
        threshold = int(self._max_tokens * self._compaction_threshold)

        if current > threshold:
            self._compaction_in_progress = True
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._run_compaction())
            except RuntimeError:
                logger.debug("auto_compaction_skipped: no running event loop")
                self._compaction_in_progress = False

    async def compact(self) -> None:
        """Manually trigger compaction using the configured compactor.

        Compatible with ``ContextCompactor`` from
        ``pnlclaw_agent.context.compaction``.
        """
        if self._compactor is None:
            return
        await self._run_compaction()

    async def _run_compaction(self) -> None:
        """Execute compaction using the configured compactor.

        The compactor must implement ``compact(messages, target_tokens)``,
        matching ``ContextCompactor.compact()`` from ``compaction.py``.
        """
        try:
            target = int(self._max_tokens * self._compaction_threshold * 0.7)
            compacted = await self._compactor.compact(self._messages, target)
            self._messages = list(compacted)
            logger.info(
                "context_compaction_complete",
                extra={"tokens_after": self.total_tokens(), "target": target},
            )
        except Exception as exc:
            logger.warning("context_compaction_failed", extra={"error": str(exc)})
        finally:
            self._compaction_in_progress = False

    # -- internal ------------------------------------------------------------

    def _trim_if_needed(self) -> None:
        """Remove oldest non-system messages until within budget."""
        while len(self._messages) > self._max_messages or self.total_tokens() > self._max_tokens:
            # Find the first non-system message to remove
            removed = False
            for i, msg in enumerate(self._messages):
                if msg.role != "system":
                    self._messages.pop(i)
                    removed = True
                    break

            if not removed:
                # Only system messages remain, can't trim further
                break
