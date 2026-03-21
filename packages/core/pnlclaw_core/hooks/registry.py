"""Hook registry: register/emit event hooks with priority ordering."""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pnlclaw_core.hooks.types import HookPriority


@dataclass(order=True)
class _HookEntry:
    """Internal entry sorted by priority (descending — higher runs first)."""

    priority: int
    handler: Any = field(compare=False)


class HookRegistry:
    """Registry for event hook handlers with priority-based execution.

    Handlers are called in descending priority order. Both sync and async
    handlers are supported.
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[_HookEntry]] = defaultdict(list)
        self._lock = threading.Lock()

    def register(
        self,
        event: str,
        handler: Any,
        *,
        priority: HookPriority | int = HookPriority.NORMAL,
    ) -> None:
        """Register a handler for an event.

        Args:
            event: Event name (e.g. 'on_market_tick').
            handler: Callable (sync or async) to invoke.
            priority: Execution priority (higher = earlier).
        """
        entry = _HookEntry(priority=int(priority), handler=handler)
        with self._lock:
            self._hooks[event].append(entry)
            self._hooks[event].sort(reverse=True)

    def emit(self, event: str, payload: dict[str, Any] | None = None) -> None:
        """Synchronously invoke all handlers for *event*.

        Async handlers are skipped in sync emit. Use ``emit_async`` for async.
        """
        if payload is None:
            payload = {}
        with self._lock:
            entries = list(self._hooks.get(event, []))
        for entry in entries:
            try:
                result = entry.handler(event, payload)
                if asyncio.iscoroutine(result):
                    result.close()  # Don't leak unawaited coroutines
            except Exception:
                pass  # Hook handlers must not crash the emitter

    async def emit_async(self, event: str, payload: dict[str, Any] | None = None) -> None:
        """Asynchronously invoke all handlers for *event*."""
        if payload is None:
            payload = {}
        with self._lock:
            entries = list(self._hooks.get(event, []))
        for entry in entries:
            try:
                result = entry.handler(event, payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    def list_events(self) -> list[str]:
        """Return all registered event names."""
        with self._lock:
            return list(self._hooks.keys())

    def clear(self) -> None:
        """Remove all registered hooks."""
        with self._lock:
            self._hooks.clear()
