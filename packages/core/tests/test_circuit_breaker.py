"""Tests for pnlclaw_core.resilience.circuit_breaker."""

import pytest

from pnlclaw_core.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_success_keeps_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        result = await cb.call(self._ok)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(self._fail)
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_rejects_calls(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=100)
        with pytest.raises(RuntimeError):
            await cb.call(self._fail)
        with pytest.raises(CircuitOpenError):
            await cb.call(self._ok)

    @pytest.mark.asyncio
    async def test_half_open_after_recovery(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        with pytest.raises(RuntimeError):
            await cb.call(self._fail)
        import asyncio

        await asyncio.sleep(0.05)
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        with pytest.raises(RuntimeError):
            await cb.call(self._fail)
        import asyncio

        await asyncio.sleep(0.05)
        result = await cb.call(self._ok)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_reset(self):
        cb = CircuitBreaker(failure_threshold=1)
        with pytest.raises(RuntimeError):
            await cb.call(self._fail)
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    @staticmethod
    async def _ok():
        return "ok"

    @staticmethod
    async def _fail():
        raise RuntimeError("fail")
