"""Token budget management — context window guardrails.

Monitors context usage and triggers recovery actions (prune → compact
→ drop oldest) when thresholds are exceeded.

Distilled from OpenClaw context window guard.
"""

from __future__ import annotations

from enum import Enum

from pnlclaw_types.agent import ChatMessage

from pnlclaw_agent.context.compaction import ContextCompactor
from pnlclaw_agent.context.pruning import ContextPruner


class BudgetStatus(str, Enum):
    """Context budget health status."""

    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    OVERFLOW = "overflow"


CHARS_PER_TOKEN = 4


class TokenBudget:
    """Token budget manager with overflow recovery cascade.

    Thresholds are defined in terms of *remaining* tokens:
    - ``OK``: remaining >= warning_threshold
    - ``WARNING``: remaining >= hard_floor
    - ``CRITICAL``: remaining > 0
    - ``OVERFLOW``: remaining <= 0

    Recovery cascade:
    1. Prune stale tool results
    2. Compact old messages (if compactor available)
    3. Drop oldest non-system messages

    Args:
        max_tokens: Total context window budget (default 200,000).
        warning_threshold: Remaining token count triggering WARNING (default 32,000).
        hard_floor: Minimum tokens reserved for new replies (default 16,000).
    """

    def __init__(
        self,
        max_tokens: int = 200_000,
        warning_threshold: int = 32_000,
        hard_floor: int = 16_000,
    ) -> None:
        self._max_tokens = max_tokens
        self._warning_threshold = warning_threshold
        self._hard_floor = hard_floor

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def check_budget(self, current_tokens: int) -> BudgetStatus:
        """Check the current budget health.

        Args:
            current_tokens: Estimated tokens currently used.

        Returns:
            BudgetStatus indicating health level.
        """
        remaining = self._max_tokens - current_tokens

        if remaining >= self._warning_threshold:
            return BudgetStatus.OK
        if remaining >= self._hard_floor:
            return BudgetStatus.WARNING
        if remaining > 0:
            return BudgetStatus.CRITICAL
        return BudgetStatus.OVERFLOW

    def get_remaining(self, current_tokens: int) -> int:
        """Get remaining token budget.

        Args:
            current_tokens: Estimated tokens currently used.

        Returns:
            Non-negative remaining tokens.
        """
        return max(0, self._max_tokens - current_tokens)

    async def recover(
        self,
        messages: list[ChatMessage],
        current_tokens: int,
        pruner: ContextPruner,
        compactor: ContextCompactor | None = None,
    ) -> list[ChatMessage]:
        """Attempt to recover from budget pressure.

        Recovery cascade:
        1. Prune stale tool results.
        2. If still critical and compactor available: compact old messages.
        3. If still overflow: drop oldest non-system messages.

        Args:
            messages: Current conversation messages.
            current_tokens: Current token usage.
            pruner: Context pruner for stale result trimming.
            compactor: Optional context compactor for summarization.

        Returns:
            Recovered message list fitting within budget.
        """
        result = list(messages)

        # Stage 1: Prune
        status = self.check_budget(current_tokens)
        if status in (BudgetStatus.WARNING, BudgetStatus.CRITICAL, BudgetStatus.OVERFLOW):
            result = pruner.prune(result, self._max_tokens)
            current_tokens = self._estimate_tokens(result)

        # Stage 2: Compact
        status = self.check_budget(current_tokens)
        if status in (BudgetStatus.CRITICAL, BudgetStatus.OVERFLOW) and compactor is not None:
            target = self._max_tokens - self._hard_floor
            try:
                result = await compactor.compact(result, target)
                current_tokens = self._estimate_tokens(result)
            except Exception:
                pass  # Compaction failed, fall through to stage 3

        # Stage 3: Drop oldest non-system messages
        status = self.check_budget(current_tokens)
        while status == BudgetStatus.OVERFLOW and len(result) > 1:
            dropped = False
            for i, msg in enumerate(result):
                if msg.role != "system":
                    result.pop(i)
                    dropped = True
                    break
            if not dropped:
                break
            current_tokens = self._estimate_tokens(result)
            status = self.check_budget(current_tokens)

        return result

    # -- internal ------------------------------------------------------------

    def _estimate_tokens(self, messages: list[ChatMessage]) -> int:
        return sum(max(1, len(m.content) // CHARS_PER_TOKEN) for m in messages)
