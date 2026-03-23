"""Tests for pnlclaw_core.plugin_sdk.discovery."""

from pnlclaw_core.plugin_sdk.discovery import DiscoveredPlugin, PluginDiscovery


class TestPluginDiscovery:
    def test_bundled_plugins(self):
        bundled = [
            DiscoveredPlugin(name="binance", module="pnlclaw_exchange_binance", source="bundled"),
        ]
        disco = PluginDiscovery(bundled=bundled)
        results = disco.discover()
        assert len(results) >= 1
        assert results[0].name == "binance"
        assert results[0].source == "bundled"

    def test_deduplication(self):
        bundled = [
            DiscoveredPlugin(name="binance", module="mod_bundled", source="bundled"),
            DiscoveredPlugin(name="binance", module="mod_user", source="user"),
        ]
        disco = PluginDiscovery(bundled=bundled)
        results = disco.discover()
        binance_plugins = [r for r in results if r.name == "binance"]
        assert len(binance_plugins) == 1
        assert binance_plugins[0].source == "bundled"  # First wins

    def test_caching(self):
        bundled = [DiscoveredPlugin(name="a", module="m", source="bundled")]
        disco = PluginDiscovery(bundled=bundled)
        r1 = disco.discover()
        r2 = disco.discover()
        assert r1 == r2

    def test_force_refresh(self):
        disco = PluginDiscovery(bundled=[])
        disco.discover()
        disco.invalidate_cache()
        results = disco.discover(force_refresh=True)
        assert isinstance(results, list)

    def test_workspace_discovery(self, tmp_path):
        # Create a fake plugin dir
        plugin_dir = tmp_path / "my_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("")

        disco = PluginDiscovery(workspace_dir=tmp_path)
        results = disco.discover()
        workspace = [r for r in results if r.source == "workspace"]
        assert len(workspace) == 1
        assert workspace[0].name == "my_plugin"

    def test_user_config_discovery(self, tmp_path):
        config = tmp_path / "plugins.yaml"
        config.write_text("plugins:\n  - name: custom\n    module: custom_plugin\n")
        disco = PluginDiscovery(user_config_path=config)
        results = disco.discover()
        user = [r for r in results if r.source == "user"]
        assert len(user) == 1
        assert user[0].name == "custom"
