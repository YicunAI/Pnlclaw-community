"""Global diagnostic event bus: subscribe/emit with recursion protection."""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_MAX_DEPTH = 100


@dataclass
class DiagnosticRecord:
    """A single diagnostic event."""

    category: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


DiagnosticHandler = Callable[[DiagnosticRecord], None]


class DiagnosticBus:
    """Global diagnostic event bus with recursion protection.

    Subscribers register for a category (or ``"*"`` for all). Emitting
    an event calls all matching handlers synchronously. Recursion is
    capped at *_MAX_DEPTH* to prevent infinite loops.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[DiagnosticHandler]] = defaultdict(list)
        self._lock = threading.Lock()
        self._depth = 0

    def subscribe(self, category: str, handler: DiagnosticHandler) -> None:
        """Register *handler* for events of *category* (or ``"*"`` for all)."""
        with self._lock:
            self._handlers[category].append(handler)

    def emit(self, event: DiagnosticRecord) -> None:
        """Dispatch *event* to matching subscribers.

        If emitting triggers further emits (recursion), stops at depth 100.
        """
        if self._depth >= _MAX_DEPTH:
            return
        self._depth += 1
        try:
            with self._lock:
                handlers = list(self._handlers.get(event.category, []))
                handlers.extend(self._handlers.get("*", []))
            for handler in handlers:
                try:
                    handler(event)
                except Exception:
                    pass  # Diagnostic handlers must not crash the emitter
        finally:
            self._depth -= 1

    def clear(self) -> None:
        """Remove all subscribers."""
        with self._lock:
            self._handlers.clear()


# Module-level singleton
_bus: DiagnosticBus | None = None
_bus_lock = threading.Lock()


def get_diagnostic_bus() -> DiagnosticBus:
    """Return the global DiagnosticBus singleton."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = DiagnosticBus()
    return _bus
