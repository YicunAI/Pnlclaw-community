"""Token cost tracker — per-session and daily LLM usage accounting.

Distilled from OpenClaw ``usage.ts``.
In-memory only for v0.1 (no persistence).
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class UsageRecord:
    """A single LLM usage record."""

    session_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tool_name: str | None = None
    timestamp: float = field(default_factory=time.time)


class TokenCostTracker:
    """Tracks LLM token usage and cost per session/day.

    In-memory only — not persisted to disk in v0.1.
    """

    def __init__(self) -> None:
        self._records: list[UsageRecord] = []

    def record_usage(
        self,
        session_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        tool_name: str | None = None,
    ) -> None:
        """Record a single LLM call's token usage.

        Args:
            session_id: Session that made the call.
            model: Model identifier (e.g. "gpt-4o").
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            cost_usd: Estimated cost in USD.
            tool_name: Optional tool that triggered this call.
        """
        self._records.append(
            UsageRecord(
                session_id=session_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                tool_name=tool_name,
            )
        )

    def get_session_cost(self, session_id: str) -> dict[str, Any]:
        """Aggregate cost for a specific session.

        Returns:
            Dict with total_input_tokens, total_output_tokens, total_tokens,
            total_cost_usd, by_tool, call_count.
        """
        filtered = [r for r in self._records if r.session_id == session_id]
        return self._aggregate(filtered)

    def get_daily_cost(self, date: str | None = None) -> dict[str, Any]:
        """Aggregate cost for a calendar day.

        Args:
            date: ISO date string (e.g. "2025-01-15"). Defaults to today.

        Returns:
            Same structure as :meth:`get_session_cost`.
        """
        if date is None:
            target = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        else:
            target = date

        filtered = [
            r
            for r in self._records
            if datetime.fromtimestamp(r.timestamp, tz=UTC).strftime("%Y-%m-%d") == target
        ]
        return self._aggregate(filtered)

    def reset(self) -> None:
        """Clear all usage records."""
        self._records.clear()

    @property
    def total_records(self) -> int:
        """Total number of usage records."""
        return len(self._records)

    # -- internal ------------------------------------------------------------

    def _aggregate(self, records: list[UsageRecord]) -> dict[str, Any]:
        """Aggregate a list of records into a summary dict."""
        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        total_cost = sum(r.cost_usd for r in records)

        by_tool: dict[str, float] = defaultdict(float)
        for r in records:
            key = r.tool_name or "(direct)"
            by_tool[key] += r.cost_usd

        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cost_usd": total_cost,
            "by_tool": dict(by_tool),
            "call_count": len(records),
        }
