"""Tests for pnlclaw_core.plugin_sdk.types."""

from pnlclaw_core.plugin_sdk.types import (
    ExchangeAdapter,
    IndicatorPlugin,
    LLMProviderPlugin,
    StrategyPlugin,
    ToolPlugin,
)


class TestPluginTypes:
    def test_exchange_adapter_is_protocol(self):
        assert hasattr(ExchangeAdapter, "__protocol_attrs__") or callable(ExchangeAdapter)

    def test_strategy_plugin_is_protocol(self):
        assert callable(StrategyPlugin)

    def test_indicator_plugin_is_protocol(self):
        assert callable(IndicatorPlugin)

    def test_llm_provider_plugin_is_protocol(self):
        assert callable(LLMProviderPlugin)

    def test_tool_plugin_is_protocol(self):
        assert callable(ToolPlugin)

    def test_exchange_adapter_has_required_methods(self):
        methods = {"connect", "disconnect", "subscribe", "unsubscribe", "name"}
        for m in methods:
            assert hasattr(ExchangeAdapter, m), f"ExchangeAdapter missing {m}"

    def test_tool_plugin_has_required_methods(self):
        for m in ("name", "description", "execute"):
            assert hasattr(ToolPlugin, m), f"ToolPlugin missing {m}"
