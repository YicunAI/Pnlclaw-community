"""Async debouncer: coalesce rapid calls within a time window."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class Debouncer:
    """Async debouncer that delays execution until a quiet period.

    Calls to ``call()`` reset the timer. The wrapped function only fires
    after *window_seconds* of silence.

    Args:
        fn: Async function to debounce.
        window_seconds: Quiet period in seconds before firing.
    """

    def __init__(self, fn: Callable[..., Awaitable[Any]], window_seconds: float = 1.0) -> None:
        self._fn = fn
        self._window = window_seconds
        self._task: asyncio.Task[None] | None = None
        self._args: tuple[Any, ...] = ()
        self._kwargs: dict[str, Any] = {}

    async def call(self, *args: Any, **kwargs: Any) -> None:
        """Schedule the debounced function, resetting the timer."""
        self._args = args
        self._kwargs = kwargs
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self._fire())

    async def _fire(self) -> None:
        """Wait for quiet period then execute."""
        await asyncio.sleep(self._window)
        await self._fn(*self._args, **self._kwargs)

    def cancel(self) -> None:
        """Cancel any pending execution."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            self._task = None
