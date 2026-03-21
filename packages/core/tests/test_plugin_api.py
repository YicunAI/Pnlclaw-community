"""Tests for pnlclaw_core.plugin_sdk.api."""

from pnlclaw_core.plugin_sdk.api import PnLClawPluginAPI


class TestPnLClawPluginAPI:
    def test_has_12_register_methods(self):
        """Spec: PnLClawPluginAPI must have 12 register_* methods."""
        methods = [m for m in dir(PnLClawPluginAPI) if m.startswith("register_")]
        assert len(methods) == 12

    def test_required_methods(self):
        expected = {
            "register_exchange",
            "register_strategy",
            "register_indicator",
            "register_llm_provider",
            "register_channel",
            "register_tool",
            "register_hook",
            "register_risk_rule",
            "register_metric",
            "register_health_check",
            "register_command",
            "register_middleware",
        }
        actual = {m for m in dir(PnLClawPluginAPI) if m.startswith("register_")}
        assert actual == expected

    def test_is_runtime_checkable(self):
        assert hasattr(PnLClawPluginAPI, "__protocol_attrs__") or hasattr(
            PnLClawPluginAPI, "__abstractmethods__"
        )
