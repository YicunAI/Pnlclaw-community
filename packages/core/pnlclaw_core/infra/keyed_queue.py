"""Keyed async queue: same key serial, different keys parallel."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class KeyedQueue:
    """Per-key serial execution queue.

    Operations with the same key are executed serially.
    Operations with different keys run in parallel.
    Useful for per-symbol order serialization.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def execute(self, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        """Execute *fn* serially for the given *key*.

        Args:
            key: Serialization key (e.g. symbol like 'BTC/USDT').
            fn: Async callable to execute.

        Returns:
            Result of *fn*.
        """
        async with self._locks[key]:
            return await fn()

    @property
    def active_keys(self) -> list[str]:
        """List keys that currently have a lock held."""
        return [k for k, lock in self._locks.items() if lock.locked()]
