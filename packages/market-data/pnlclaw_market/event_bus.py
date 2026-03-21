"""Internal async event bus: type-safe subscribe/publish pattern.

Supports multiple listeners per event type and both sync and async callbacks.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)

# Callback can be sync or async, receiving a single event argument
EventCallback = Callable[[Any], Any] | Callable[[Any], Awaitable[Any]]


class EventBus:
    """Type-safe internal event bus.

    Subscribers register for a specific event type (by class). When an event
    is published, all matching callbacks are invoked. Both sync and async
    callbacks are supported.

    Thread-safe for subscription management. Publishing should happen from
    the asyncio event loop or a synchronous context (sync callbacks only).

    Example::

        bus = EventBus()
        bus.subscribe(TickerEvent, my_handler)
        bus.publish(ticker_event)  # dispatches to my_handler
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[EventCallback]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event_type: type[T], callback: Callable[[T], Any]) -> None:
        """Register *callback* for events of *event_type*.

        Args:
            event_type: The class of events to listen for.
            callback: Function to invoke when event is published. May be sync or async.
        """
        with self._lock:
            self._handlers[event_type].append(callback)

    def unsubscribe(self, event_type: type[T], callback: Callable[[T], Any]) -> None:
        """Remove *callback* from listeners of *event_type*.

        No-op if the callback was not registered.
        """
        with self._lock:
            handlers = self._handlers.get(event_type, [])
            try:
                handlers.remove(callback)
            except ValueError:
                pass

    def publish(self, event: Any) -> None:
        """Dispatch *event* to all registered handlers for its type.

        Sync callbacks are invoked directly. Async callbacks are scheduled
        via the running event loop (fire-and-forget).

        If no event loop is running, async callbacks are skipped with a warning.
        """
        event_type = type(event)
        with self._lock:
            handlers = list(self._handlers.get(event_type, []))

        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    self._schedule_async(handler, event)
                else:
                    handler(event)
            except Exception:
                logger.exception(
                    "Error in event handler %s for %s",
                    getattr(handler, "__name__", repr(handler)),
                    event_type.__name__,
                )

    async def publish_async(self, event: Any) -> None:
        """Dispatch *event* to all handlers, awaiting async callbacks.

        Use this variant when calling from an async context and you need
        to ensure all handlers complete before continuing.
        """
        event_type = type(event)
        with self._lock:
            handlers = list(self._handlers.get(event_type, []))

        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception:
                logger.exception(
                    "Error in event handler %s for %s",
                    getattr(handler, "__name__", repr(handler)),
                    event_type.__name__,
                )

    def clear(self) -> None:
        """Remove all subscribers."""
        with self._lock:
            self._handlers.clear()

    def handler_count(self, event_type: type) -> int:
        """Return the number of registered handlers for *event_type*."""
        with self._lock:
            return len(self._handlers.get(event_type, []))

    def _schedule_async(self, handler: Callable[..., Awaitable[Any]], event: Any) -> None:
        """Schedule an async handler on the running loop, or warn if none."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._safe_async_call(handler, event))
        except RuntimeError:
            logger.warning(
                "No running event loop; skipping async handler %s",
                getattr(handler, "__name__", repr(handler)),
            )

    @staticmethod
    async def _safe_async_call(handler: Callable[..., Awaitable[Any]], event: Any) -> None:
        """Invoke an async handler, catching exceptions."""
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "Error in async event handler %s",
                getattr(handler, "__name__", repr(handler)),
            )
