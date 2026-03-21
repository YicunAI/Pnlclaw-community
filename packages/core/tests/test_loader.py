"""Tests for pnlclaw_core.plugin_sdk.loader."""


import pytest

from pnlclaw_core.plugin_sdk.loader import PluginLoader, PluginManifest


class TestPluginManifest:
    def test_minimal(self):
        m = PluginManifest(name="test")
        assert m.name == "test"
        assert m.version == "0.0.0"
        assert m.capabilities == []

    def test_full(self):
        m = PluginManifest(
            name="binance",
            version="1.0.0",
            description="Binance adapter",
            capabilities=["exchange"],
            entry_point="binance_plugin:setup",
        )
        assert m.entry_point == "binance_plugin:setup"


class TestPluginLoader:
    def test_load_stdlib_module(self):
        loader = PluginLoader()
        result = loader.load("json")
        assert result.name == "json"  # Falls back to module name
        assert result.module is not None

    def test_load_nonexistent_raises(self):
        loader = PluginLoader()
        with pytest.raises(ImportError):
            loader.load("nonexistent_module_xyz_123")

    def test_load_entry_point(self):
        loader = PluginLoader()
        result = loader.load_entry_point("json:dumps")
        assert result.module is not None
        assert result.setup_fn is not None  # json.dumps exists
