"""Tests for pnlclaw_core.infra.debounce."""

import asyncio

import pytest

from pnlclaw_core.infra.debounce import Debouncer


class TestDebouncer:
    @pytest.mark.asyncio
    async def test_fires_after_quiet_period(self):
        results = []

        async def fn(value):
            results.append(value)

        d = Debouncer(fn, window_seconds=0.05)
        await d.call("first")
        await asyncio.sleep(0.1)
        assert results == ["first"]

    @pytest.mark.asyncio
    async def test_resets_on_new_call(self):
        results = []

        async def fn(value):
            results.append(value)

        d = Debouncer(fn, window_seconds=0.1)
        await d.call("a")
        await asyncio.sleep(0.05)
        await d.call("b")  # Resets timer
        await asyncio.sleep(0.15)
        # Only "b" should fire (last call wins)
        assert results == ["b"]

    @pytest.mark.asyncio
    async def test_cancel(self):
        results = []

        async def fn():
            results.append(1)

        d = Debouncer(fn, window_seconds=0.05)
        await d.call()
        d.cancel()
        await asyncio.sleep(0.1)
        assert results == []
