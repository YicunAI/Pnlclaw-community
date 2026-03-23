"""Tests for pnlclaw_core.config."""

from pnlclaw_core.config import PnLClawConfig, load_config


class TestPnLClawConfig:
    def test_defaults(self):
        c = PnLClawConfig()
        assert c.env == "development"
        assert c.api_port == 8080
        assert c.enable_real_trading is False

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("PNLCLAW_API_PORT", "9090")
        monkeypatch.setenv("PNLCLAW_LOG_LEVEL", "DEBUG")
        c = PnLClawConfig()
        assert c.api_port == 9090
        assert c.log_level == "DEBUG"


class TestLoadConfig:
    def test_load_with_yaml(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("api_port: 7777\nlog_level: WARNING\n")
        c = load_config(config_path=config_file)
        assert c.api_port == 7777
        assert c.log_level == "WARNING"

    def test_env_overrides_yaml(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("api_port: 7777\n")
        monkeypatch.setenv("PNLCLAW_API_PORT", "5555")
        c = load_config(config_path=config_file)
        assert c.api_port == 5555

    def test_kwarg_overrides(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("api_port: 7777\n")
        c = load_config(config_path=config_file, api_port=3333)
        assert c.api_port == 3333

    def test_missing_yaml_uses_defaults(self, tmp_path):
        c = load_config(config_path=tmp_path / "nonexistent.yaml")
        assert c.api_port == 8080
