"""Context pruning — TTL-based tool result trimming.

Reduces context size by trimming or clearing stale tool results.

Distilled from OpenClaw context pruning.
"""

from __future__ import annotations

import copy
import time

from pnlclaw_types.agent import ChatMessage


class ContextPruner:
    """Prunes stale tool results from conversation context.

    Three-stage approach:
    1. **TTL**: identify tool results older than ``ttl_seconds``.
    2. **Soft trim**: keep first/last 1500 chars when budget > 30%.
    3. **Hard clear**: replace with placeholder when budget > 50%.
    """

    CHARS_PER_TOKEN = 4

    def __init__(
        self,
        ttl_seconds: float = 300.0,
        soft_threshold: float = 0.3,
        hard_threshold: float = 0.5,
    ) -> None:
        self._ttl_ms = int(ttl_seconds * 1000)
        self._soft_threshold = soft_threshold
        self._hard_threshold = hard_threshold

    def prune(
        self, messages: list[ChatMessage], budget_tokens: int
    ) -> list[ChatMessage]:
        """Prune stale tool results to fit within token budget.

        Returns a new list — does not modify the input.

        Args:
            messages: Conversation message list.
            budget_tokens: Total context token budget.

        Returns:
            Pruned copy of the message list.
        """
        now_ms = int(time.time() * 1000)
        result = [self._copy_msg(m) for m in messages]

        current_tokens = self._total_tokens(result)

        # Stage 1: identify stale tool results
        stale_indices = [
            i for i, m in enumerate(result)
            if m.role == "tool" and (now_ms - m.timestamp) > self._ttl_ms
        ]

        if not stale_indices:
            return result

        # Stage 2: soft trim if above 30% budget
        if current_tokens > budget_tokens * self._soft_threshold:
            for i in stale_indices:
                content = result[i].content
                if len(content) > 3200:  # Only trim if substantial
                    head = content[:1500]
                    tail = content[-1500:]
                    trimmed_chars = len(content) - 3000
                    result[i] = ChatMessage(
                        role=result[i].role,
                        content=f"{head}\n[... trimmed {trimmed_chars} chars ...]\n{tail}",
                        timestamp=result[i].timestamp,
                        metadata=result[i].metadata,
                    )

        current_tokens = self._total_tokens(result)

        # Stage 3: hard clear if still above 50% budget
        if current_tokens > budget_tokens * self._hard_threshold:
            for i in stale_indices:
                if result[i].content != "[Old tool result cleared]":
                    result[i] = ChatMessage(
                        role=result[i].role,
                        content="[Old tool result cleared]",
                        timestamp=result[i].timestamp,
                        metadata=result[i].metadata,
                    )

        return result

    # -- internal ------------------------------------------------------------

    def _total_tokens(self, messages: list[ChatMessage]) -> int:
        return sum(max(1, len(m.content) // self.CHARS_PER_TOKEN) for m in messages)

    def _copy_msg(self, msg: ChatMessage) -> ChatMessage:
        return ChatMessage(
            role=msg.role,
            content=msg.content,
            timestamp=msg.timestamp,
            metadata=msg.metadata,
        )
