"""Tests for pnlclaw_core.plugin_sdk.registry."""

import pytest

from pnlclaw_core.plugin_sdk.registry import PluginRegistry


class TestPluginRegistry:
    def setup_method(self):
        PluginRegistry.reset()

    def test_singleton(self):
        a = PluginRegistry()
        b = PluginRegistry()
        assert a is b

    def test_register_and_get(self):
        reg = PluginRegistry()
        reg.register("exchange", "binance", {"adapter": True})
        assert reg.get("exchange", "binance") == {"adapter": True}

    def test_get_missing_returns_none(self):
        reg = PluginRegistry()
        assert reg.get("exchange", "unknown") is None

    def test_duplicate_raises(self):
        reg = PluginRegistry()
        reg.register("exchange", "binance", {})
        with pytest.raises(ValueError, match="already registered"):
            reg.register("exchange", "binance", {})

    def test_list_plugins(self):
        reg = PluginRegistry()
        reg.register("indicator", "sma", {"type": "sma"})
        reg.register("indicator", "ema", {"type": "ema"})
        result = reg.list("indicator")
        assert len(result) == 2
        assert "sma" in result
        assert "ema" in result

    def test_list_capabilities(self):
        reg = PluginRegistry()
        reg.register("exchange", "binance", {})
        reg.register("indicator", "sma", {})
        caps = reg.list_capabilities()
        assert "exchange" in caps
        assert "indicator" in caps

    def test_clear(self):
        reg = PluginRegistry()
        reg.register("exchange", "binance", {})
        reg.clear()
        assert reg.get("exchange", "binance") is None
