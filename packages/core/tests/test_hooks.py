"""Tests for pnlclaw_core.hooks."""

import pytest

from pnlclaw_core.hooks.registry import HookRegistry
from pnlclaw_core.hooks.types import PREDEFINED_HOOKS, HookPriority


class TestHookRegistry:
    def test_register_and_emit(self):
        reg = HookRegistry()
        received = []
        reg.register("on_signal", lambda e, p: received.append(p))
        reg.emit("on_signal", {"symbol": "BTC/USDT"})
        assert len(received) == 1
        assert received[0]["symbol"] == "BTC/USDT"

    def test_priority_ordering(self):
        reg = HookRegistry()
        order = []
        reg.register("evt", lambda e, p: order.append("low"), priority=HookPriority.LOW)
        reg.register("evt", lambda e, p: order.append("high"), priority=HookPriority.HIGH)
        reg.register("evt", lambda e, p: order.append("normal"), priority=HookPriority.NORMAL)
        reg.emit("evt")
        assert order == ["high", "normal", "low"]

    def test_handler_exception_does_not_crash(self):
        reg = HookRegistry()
        reg.register("evt", lambda e, p: 1 / 0)
        reg.emit("evt")  # Should not raise

    @pytest.mark.asyncio
    async def test_emit_async(self):
        reg = HookRegistry()
        received = []

        async def handler(event, payload):
            received.append(payload)

        reg.register("evt", handler)
        await reg.emit_async("evt", {"data": 1})
        assert len(received) == 1

    def test_list_events(self):
        reg = HookRegistry()
        reg.register("a", lambda e, p: None)
        reg.register("b", lambda e, p: None)
        assert set(reg.list_events()) == {"a", "b"}

    def test_clear(self):
        reg = HookRegistry()
        reg.register("a", lambda e, p: None)
        reg.clear()
        assert reg.list_events() == []


class TestPredefinedHooks:
    def test_has_5_predefined(self):
        assert len(PREDEFINED_HOOKS) == 5
        assert "on_market_tick" in PREDEFINED_HOOKS
        assert "on_signal" in PREDEFINED_HOOKS
        assert "on_order_placed" in PREDEFINED_HOOKS
        assert "on_risk_triggered" in PREDEFINED_HOOKS
        assert "on_backtest_complete" in PREDEFINED_HOOKS
