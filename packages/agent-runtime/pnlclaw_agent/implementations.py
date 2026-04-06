"""Basic implementations for Protocol interfaces.

These are minimal, functional implementations suitable for local
single-user workflows. Advanced implementations can be substituted
via the ComponentRegistry.
"""

from __future__ import annotations

from typing import Any

from pnlclaw_agent.protocols import MemoryEntry


class KeywordMemoryBackend:
    """Community memory backend using keyword matching.

    Stores entries in-memory and recalls via substring matching.
    """

    def __init__(self) -> None:
        self._entries: list[MemoryEntry] = []

    async def store(self, entry: MemoryEntry) -> None:
        self._entries.append(entry)

    async def recall(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        query_lower = query.lower()
        matches = [e for e in self._entries if query_lower in e.content.lower()]
        return matches[:limit]

    # --- PRO-BEGIN ---
    async def semantic_recall(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        raise NotImplementedError("Semantic recall is not available in this edition")
    # --- PRO-END ---


class SingleAgentRunner:
    """Community orchestrator that runs a single agent (no delegation)."""

    async def run(self, task: str, context: dict[str, Any]) -> str:
        return f"Task acknowledged: {task}"

    # --- PRO-BEGIN ---
    async def delegate(self, request: Any) -> Any:
        raise NotImplementedError("Multi-agent delegation is not available in this edition")
    # --- PRO-END ---


class FixedModelRouter:
    """Community model router that returns a fixed model identifier."""

    def __init__(self, model: str = "default") -> None:
        self._model = model

    def route(self, messages: list[dict[str, Any]]) -> str:
        return self._model

    # --- PRO-BEGIN ---
    def select_for_task(self, task_type: Any) -> Any:
        raise NotImplementedError("Smart model routing is not available in this edition")
    # --- PRO-END ---


class BasicContextManager:
    """Community context engine with basic FIFO management."""

    def __init__(self) -> None:
        self._data: list[dict[str, Any]] = []
        self._config: dict[str, Any] = {}

    async def bootstrap(self, config: dict[str, Any]) -> None:
        self._config = config

    async def ingest(self, data: dict[str, Any]) -> None:
        self._data.append(data)

    async def assemble(self, budget: int) -> list[dict[str, Any]]:
        return self._data[-budget:] if budget > 0 else self._data

    async def compact(self) -> None:
        if len(self._data) > 100:
            self._data = self._data[-50:]


class RuleBasedFeedback:
    """Community feedback engine using rule-based analysis."""

    async def analyze(self, result: dict[str, Any]) -> dict[str, Any]:
        analysis: dict[str, Any] = {"status": "analyzed"}
        sharpe = result.get("sharpe_ratio", 0)
        if isinstance(sharpe, (int, float)):
            if sharpe < 0:
                analysis["recommendation"] = "Strategy underperforms risk-free rate"
            elif sharpe < 1:
                analysis["recommendation"] = "Strategy needs improvement"
            else:
                analysis["recommendation"] = "Strategy shows acceptable risk-adjusted returns"
        return analysis

    # --- PRO-BEGIN ---
    async def iterate(self, plan: Any) -> Any:
        raise NotImplementedError("AI feedback iteration is not available in this edition")
    # --- PRO-END ---
