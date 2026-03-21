"""Tests for pnlclaw_core.infra.keyed_queue."""

import asyncio

import pytest

from pnlclaw_core.infra.keyed_queue import KeyedQueue


class TestKeyedQueue:
    @pytest.mark.asyncio
    async def test_same_key_serial(self):
        q = KeyedQueue()
        order = []

        async def task(name, delay):
            order.append(f"{name}_start")
            await asyncio.sleep(delay)
            order.append(f"{name}_end")

        t1 = asyncio.create_task(q.execute("BTC", lambda: task("a", 0.05)))
        t2 = asyncio.create_task(q.execute("BTC", lambda: task("b", 0.01)))
        await asyncio.gather(t1, t2)
        # a must finish before b starts (serial for same key)
        assert order.index("a_end") < order.index("b_start")

    @pytest.mark.asyncio
    async def test_different_keys_parallel(self):
        q = KeyedQueue()
        order = []

        async def task(name, delay):
            order.append(f"{name}_start")
            await asyncio.sleep(delay)
            order.append(f"{name}_end")

        t1 = asyncio.create_task(q.execute("BTC", lambda: task("btc", 0.05)))
        t2 = asyncio.create_task(q.execute("ETH", lambda: task("eth", 0.05)))
        await asyncio.gather(t1, t2)
        # Both should start before either finishes (parallel)
        assert order.index("btc_start") < order.index("btc_end")
        assert order.index("eth_start") < order.index("eth_end")

    @pytest.mark.asyncio
    async def test_returns_result(self):
        q = KeyedQueue()

        async def fn():
            return 42

        result = await q.execute("key", fn)
        assert result == 42
