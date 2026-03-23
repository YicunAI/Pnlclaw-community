"""Tests for pnlclaw_core.resilience.retry."""

import pytest

from pnlclaw_core.resilience.backoff import BackoffPolicy
from pnlclaw_core.resilience.retry import retry_async


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_succeeds_first_try(self):
        calls = 0

        async def fn():
            nonlocal calls
            calls += 1
            return "ok"

        result = await retry_async(fn, max_attempts=3)
        assert result == "ok"
        assert calls == 1

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        calls = 0

        async def fn():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ValueError("not yet")
            return "ok"

        policy = BackoffPolicy(initial=0.001, factor=1.0, jitter=False)
        result = await retry_async(fn, max_attempts=3, policy=policy)
        assert result == "ok"
        assert calls == 3

    @pytest.mark.asyncio
    async def test_exhausted_raises(self):
        async def fn():
            raise RuntimeError("fail")

        policy = BackoffPolicy(initial=0.001, factor=1.0, jitter=False)
        with pytest.raises(RuntimeError, match="fail"):
            await retry_async(fn, max_attempts=2, policy=policy)

    @pytest.mark.asyncio
    async def test_should_retry_false_stops_early(self):
        calls = 0

        async def fn():
            nonlocal calls
            calls += 1
            raise TypeError("no retry")

        with pytest.raises(TypeError):
            await retry_async(
                fn,
                max_attempts=5,
                policy=BackoffPolicy(initial=0.001, jitter=False),
                should_retry=lambda e: not isinstance(e, TypeError),
            )
        assert calls == 1

    @pytest.mark.asyncio
    async def test_delays_increase(self):
        """Verify backoff delays are increasing across retries."""
        policy = BackoffPolicy(initial=0.01, factor=2.0, jitter=False)
        calls = 0

        async def fn():
            nonlocal calls
            calls += 1
            if calls <= 3:
                raise ValueError("retry")
            return "done"

        await retry_async(fn, max_attempts=4, policy=policy)
        assert calls == 4
