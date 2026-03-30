"""Protocol interfaces for PnLClaw Open Core architecture.

Defines six Protocol interfaces that serve as the Community/Pro boundary.
Community edition registers basic implementations; Pro edition replaces
them with advanced implementations via ``ComponentRegistry.replace()``.

Architecture: AGPL Community (this file) + closed-source Pro extension.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class MemoryBackend(Protocol):
    """Memory backend — Community: keyword matching; Pro: vector semantic search."""

    async def store(self, entry: "MemoryEntry") -> None:
        """Store a memory entry."""
        ...

    async def recall(self, query: str, limit: int = 10) -> list["MemoryEntry"]:
        """Recall memory entries matching the query."""
        ...

    async def semantic_recall(self, query: str, limit: int = 10) -> list["MemoryEntry"]:
        """PRO RESERVED: Semantic vector similarity search."""
        raise NotImplementedError("Semantic recall requires PnLClaw Pro")


@runtime_checkable
class AgentOrchestrator(Protocol):
    """Agent orchestration — Community: single agent; Pro: multi-agent collaboration."""

    async def run(self, task: str, context: dict[str, Any]) -> str:
        """Run a task with a single agent."""
        ...

    async def delegate(self, request: "DelegationRequest") -> "ConsensusResult":
        """PRO RESERVED: Delegate task to multiple agents for consensus."""
        raise NotImplementedError("Multi-agent delegation requires PnLClaw Pro")


@runtime_checkable
class ModelRouter(Protocol):
    """Model routing — Community: fixed single model; Pro: smart dynamic selection."""

    def route(self, messages: list[dict[str, Any]]) -> str:
        """Return the model identifier to use for the given messages."""
        ...

    def select_for_task(self, task_type: "TaskType") -> "ModelProfile":
        """PRO RESERVED: Select optimal model based on task type."""
        raise NotImplementedError("Smart model routing requires PnLClaw Pro")


@runtime_checkable
class ContextEngine(Protocol):
    """Context engine — Community: basic management; Pro: advanced pluggable engine."""

    async def bootstrap(self, config: dict[str, Any]) -> None:
        """Initialize the context engine with configuration."""
        ...

    async def ingest(self, data: dict[str, Any]) -> None:
        """Ingest new data into the context."""
        ...

    async def assemble(self, budget: int) -> list[dict[str, Any]]:
        """Assemble context within the given token budget."""
        ...

    async def compact(self) -> None:
        """Compact/compress the stored context."""
        ...


@runtime_checkable
class FeedbackEngine(Protocol):
    """Feedback engine — Community: rule-based detection; Pro: AI auto-iteration."""

    async def analyze(self, result: dict[str, Any]) -> dict[str, Any]:
        """Analyze a strategy/backtest result."""
        ...

    async def iterate(self, plan: "IterationPlan") -> "OptimizationResult":
        """PRO RESERVED: AI-driven iterative optimization."""
        raise NotImplementedError("AI feedback iteration requires PnLClaw Pro")


@runtime_checkable
class MarketScanner(Protocol):
    """Market scanner — Community: disabled; Pro: 7x24 automated scanning.

    This entire Protocol is PRO RESERVED. Community edition does not
    register an implementation.
    """

    async def scan(self, symbols: list[str]) -> list["ScanResult"]:
        """PRO RESERVED: Scan markets for anomalies."""
        raise NotImplementedError("Market scanning requires PnLClaw Pro")


# ---------------------------------------------------------------------------
# PRO RESERVED data structures (defined but not implemented)
# ---------------------------------------------------------------------------


@dataclass
class MemoryEntry:
    """A single memory entry for recall."""

    id: str = ""
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass
class DelegationRequest:
    """Multi-agent delegation request."""

    task: str = ""
    agents: list[str] = field(default_factory=list)
    strategy: str = "parallel"  # parallel | sequential | debate


@dataclass
class ConsensusResult:
    """Multi-agent consensus result."""

    conclusion: str = ""
    confidence: float = 0.0
    dissenting_views: list[str] | None = None


@dataclass
class EmbeddingVector:
    """Vector embedding for semantic memory."""

    values: list[float] = field(default_factory=list)
    model: str = ""
    dimensions: int = 0


@dataclass
class SimilarityScore:
    """Similarity score for memory recall."""

    score: float = 0.0
    entry_id: str = ""


class TaskType:
    """Task type classification for smart model routing."""

    ANALYSIS = "analysis"
    STRATEGY = "strategy"
    RISK = "risk"
    EXPLANATION = "explanation"


@dataclass
class ModelProfile:
    """Model configuration profile for task-based routing."""

    model_id: str = ""
    provider: str = ""
    max_tokens: int = 4096
    cost_per_1k: float = 0.0


@dataclass
class ScanResult:
    """Market scan result with detected anomalies."""

    symbol: str = ""
    anomalies: list["Anomaly"] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class Anomaly:
    """A detected market anomaly."""

    type: str = ""  # volume_spike | price_deviation | funding_rate
    severity: str = ""  # low | medium | high
    description: str = ""


@dataclass
class IterationPlan:
    """Strategy optimization iteration plan."""

    strategy_id: str = ""
    parameters_to_optimize: list[str] = field(default_factory=list)
    max_iterations: int = 50


@dataclass
class OptimizationResult:
    """Strategy optimization result."""

    best_params: dict[str, Any] = field(default_factory=dict)
    improvement_pct: float = 0.0
    iterations_run: int = 0
