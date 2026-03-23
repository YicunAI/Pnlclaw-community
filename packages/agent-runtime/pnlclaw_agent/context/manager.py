"""Context manager — maintains conversation history with token budgeting.

Tracks messages, estimates token usage, and auto-trims when the
conversation exceeds the configured budget.
"""

from __future__ import annotations

import time
from typing import Any

from pnlclaw_types.agent import ChatMessage


class ContextManager:
    """Manages agent conversation history with token budget enforcement.

    Uses a simple heuristic (4 chars ≈ 1 token) for token estimation.
    Automatically trims oldest non-system messages when the context
    exceeds ``max_tokens`` or ``max_messages``.
    """

    # Estimation: 4 characters ≈ 1 token
    CHARS_PER_TOKEN = 4

    def __init__(
        self,
        max_tokens: int = 200_000,
        max_messages: int = 100,
    ) -> None:
        self._messages: list[ChatMessage] = []
        self._max_tokens = max_tokens
        self._max_messages = max_messages

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

    def get_messages(self) -> list[ChatMessage]:
        """Return the current conversation history."""
        return list(self._messages)

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text string (4 chars ≈ 1 token)."""
        return max(1, len(text) // self.CHARS_PER_TOKEN)

    def total_tokens(self) -> int:
        """Estimate total tokens across all messages."""
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

    @property
    def message_count(self) -> int:
        """Number of messages in history."""
        return len(self._messages)

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
