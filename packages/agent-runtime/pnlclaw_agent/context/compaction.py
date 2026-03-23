"""Context compaction — summarize old messages to free token budget.

Uses an injected ``SummarizerProtocol`` (backed by an LLM) to compress
old conversation turns into concise summaries.

Distilled from OpenClaw context compaction.
"""

from __future__ import annotations

import re
import time
from typing import Protocol

from pnlclaw_types.agent import ChatMessage

# ---------------------------------------------------------------------------
# Summarizer protocol (injected, no direct pnlclaw_llm import)
# ---------------------------------------------------------------------------


class SummarizerProtocol(Protocol):
    """Protocol for message summarization.

    Implementations should wrap an LLM call (e.g. ``LLMProvider.chat``)
    with a summarization prompt.
    """

    async def summarize(self, text: str) -> str:
        """Summarize the given text into a concise form."""
        ...


# ---------------------------------------------------------------------------
# Identifier preservation
# ---------------------------------------------------------------------------

# Patterns for identifiers that must survive summarization
_IDENTIFIER_PATTERNS = [
    re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", re.I),  # UUIDs
    re.compile(r"bt-[a-f0-9]+", re.I),  # backtest IDs
    re.compile(r"ord-[a-f0-9]+", re.I),  # order IDs
    re.compile(r"strat-[a-f0-9]+", re.I),  # strategy IDs
    re.compile(r"https?://\S+"),  # URLs
    re.compile(r"[A-Z]{2,10}/[A-Z]{2,10}"),  # Symbol pairs like BTC/USDT
]


def _extract_identifiers(text: str) -> set[str]:
    """Extract all preservable identifiers from text."""
    ids: set[str] = set()
    for pattern in _IDENTIFIER_PATTERNS:
        ids.update(pattern.findall(text))
    return ids


# ---------------------------------------------------------------------------
# Compactor
# ---------------------------------------------------------------------------

CHARS_PER_TOKEN = 4


class ContextCompactor:
    """Compresses old conversation messages via summarization.

    Falls back gracefully when no summarizer is available:
    1. Full summarization (if summarizer available)
    2. Partial summarization (only largest chunk)
    3. Size-only compaction marker

    Args:
        summarizer: Optional summarizer (typically LLM-backed).
    """

    def __init__(self, summarizer: SummarizerProtocol | None = None) -> None:
        self._summarizer = summarizer

    async def compact(
        self,
        messages: list[ChatMessage],
        target_tokens: int,
    ) -> list[ChatMessage]:
        """Compact messages to fit within target token count.

        Returns a new message list with old turns summarized.

        Args:
            messages: Full conversation history.
            target_tokens: Target token budget to fit within.

        Returns:
            Compacted message list.
        """
        current_tokens = self._total_tokens(messages)
        if current_tokens <= target_tokens:
            return list(messages)

        # Identify chunks of old messages eligible for compaction
        # Keep system messages and the last few messages intact
        protected_count = min(6, len(messages))
        compactable = messages[:-protected_count] if protected_count < len(messages) else []
        protected = (
            messages[-protected_count:] if protected_count < len(messages) else list(messages)
        )

        if not compactable:
            return list(messages)

        # Build chunks (groups of 3-5 messages)
        chunks = self._build_chunks(compactable)

        if self._summarizer is not None:
            # Try full summarization
            try:
                compacted = await self._summarize_chunks(chunks)
                result = compacted + protected
                if self._total_tokens(result) <= target_tokens:
                    return result
            except Exception:
                pass

            # Try partial summarization (only the largest chunk)
            try:
                largest_idx = max(
                    range(len(chunks)), key=lambda i: sum(len(m.content) for m in chunks[i])
                )
                partial = list(chunks)
                partial[largest_idx] = [await self._summarize_single(chunks[largest_idx])]
                flat = [m for chunk in partial for m in chunk]
                result = flat + protected
                if self._total_tokens(result) <= target_tokens:
                    return result
            except Exception:
                pass

        # Fallback: size-only compaction marker
        total_compacted_tokens = self._total_tokens(compactable)
        marker = ChatMessage(
            role="system",
            content=(
                f"[{len(compactable)} messages compacted, ~{total_compacted_tokens} tokens freed]"
            ),
            timestamp=int(time.time() * 1000),
        )
        return [marker] + protected

    # -- internal ------------------------------------------------------------

    def _build_chunks(
        self, messages: list[ChatMessage], chunk_size: int = 4
    ) -> list[list[ChatMessage]]:
        """Group messages into chunks of approximately ``chunk_size``."""
        chunks: list[list[ChatMessage]] = []
        current: list[ChatMessage] = []

        for msg in messages:
            # Don't include system messages in chunks
            if msg.role == "system":
                if current:
                    chunks.append(current)
                    current = []
                chunks.append([msg])  # system messages stay as-is
                continue

            current.append(msg)
            if len(current) >= chunk_size:
                chunks.append(current)
                current = []

        if current:
            chunks.append(current)

        return chunks

    async def _summarize_chunks(self, chunks: list[list[ChatMessage]]) -> list[ChatMessage]:
        """Summarize each chunk, preserving identifiers."""
        result: list[ChatMessage] = []

        for i, chunk in enumerate(chunks):
            # System messages pass through
            if len(chunk) == 1 and chunk[0].role == "system":
                result.append(chunk[0])
                continue

            result.append(await self._summarize_single(chunk, index=i))

        return result

    async def _summarize_single(self, chunk: list[ChatMessage], index: int = 0) -> ChatMessage:
        """Summarize a single chunk into one message."""
        assert self._summarizer is not None

        # Combine chunk text
        combined = "\n".join(f"[{m.role}]: {m.content}" for m in chunk)

        # Extract identifiers to preserve
        identifiers = _extract_identifiers(combined)

        summary = await self._summarizer.summarize(combined)

        # Append any missing identifiers
        summary_ids = _extract_identifiers(summary)
        missing = identifiers - summary_ids
        if missing:
            summary += f"\n[Referenced IDs: {', '.join(sorted(missing))}]"

        start_idx = index * 4
        end_idx = start_idx + len(chunk) - 1

        return ChatMessage(
            role="system",
            content=f"[Summary of turns {start_idx}-{end_idx}]: {summary}",
            timestamp=chunk[-1].timestamp if chunk else int(time.time() * 1000),
        )

    def _total_tokens(self, messages: list[ChatMessage]) -> int:
        return sum(max(1, len(m.content) // CHARS_PER_TOKEN) for m in messages)
