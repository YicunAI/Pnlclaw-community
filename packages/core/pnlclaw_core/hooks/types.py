"""Hook system types: priority enum and handler protocol."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Protocol, runtime_checkable


class HookPriority(IntEnum):
    """Execution priority for hook handlers. Higher value = runs earlier."""

    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@runtime_checkable
class HookHandler(Protocol):
    """Protocol for synchronous hook handlers."""

    def __call__(self, event: str, payload: dict[str, Any]) -> None: ...


@runtime_checkable
class AsyncHookHandler(Protocol):
    """Protocol for async hook handlers."""

    async def __call__(self, event: str, payload: dict[str, Any]) -> None: ...


# Predefined quantitative hook events
HOOK_ON_MARKET_TICK = "on_market_tick"
HOOK_ON_SIGNAL = "on_signal"
HOOK_ON_ORDER_PLACED = "on_order_placed"
HOOK_ON_RISK_TRIGGERED = "on_risk_triggered"
HOOK_ON_BACKTEST_COMPLETE = "on_backtest_complete"

PREDEFINED_HOOKS: set[str] = {
    HOOK_ON_MARKET_TICK,
    HOOK_ON_SIGNAL,
    HOOK_ON_ORDER_PLACED,
    HOOK_ON_RISK_TRIGGERED,
    HOOK_ON_BACKTEST_COMPLETE,
}
