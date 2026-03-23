"""Configuration loading: YAML file + environment variable overrides + Pydantic validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning empty dict if missing or invalid."""
    if not path.is_file():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


# Module-level store for YAML values (set before constructing config)
_yaml_values: dict[str, Any] = {}


class _YamlSettingsSource(PydanticBaseSettingsSource):
    """Settings source that reads from a pre-loaded YAML dict."""

    def get_field_value(self, field, field_name):  # type: ignore[override]
        value = _yaml_values.get(field_name)
        return value, field_name, value is not None

    def __call__(self) -> dict[str, Any]:
        return {k: v for k, v in _yaml_values.items() if v is not None}


class PnLClawConfig(BaseSettings):
    """Central configuration for PnLClaw.

    Values are loaded in order of priority (highest wins):
    1. Init kwargs / explicit overrides
    2. Environment variables (prefixed ``PNLCLAW_``)
    3. ``~/.pnlclaw/config.yaml``
    4. Field defaults
    """

    model_config = {"env_prefix": "PNLCLAW_"}

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, _YamlSettingsSource(settings_cls))

    # --- App ---
    env: str = Field("development", description="Runtime environment")
    log_level: str = Field("INFO", description="Logging level")

    # --- Paths ---
    data_dir: str = Field("./data", description="Data directory")
    db_path: str = Field("./data/pnlclaw.db", description="SQLite database path")
    log_dir: str = Field("./logs", description="Log output directory")

    # --- Local API ---
    api_host: str = Field("127.0.0.1", description="API bind host")
    api_port: int = Field(8080, description="API bind port")

    # --- Exchange ---
    default_exchange: str = Field("binance", description="Default exchange")
    default_symbol: str = Field("BTCUSDT", description="Default trading symbol")

    # --- LLM ---
    llm_provider: str = Field("openai_compatible", description="LLM provider name")
    llm_base_url: str = Field("", description="LLM API base URL")
    llm_model: str = Field("", description="LLM model name")
    llm_timeout_seconds: int = Field(60, description="LLM request timeout")

    # --- Safety ---
    enable_real_trading: bool = Field(False, description="Enable real-money trading")
    paper_starting_balance: float = Field(10000.0, description="Paper trading initial balance")


def load_config(
    config_path: Path | None = None,
    **overrides: Any,
) -> PnLClawConfig:
    """Load configuration with YAML → env → overrides precedence.

    Args:
        config_path: Explicit path to YAML config. Defaults to ``~/.pnlclaw/config.yaml``.
        **overrides: Additional keyword overrides (highest priority).

    Returns:
        Validated ``PnLClawConfig`` instance.
    """
    if config_path is None:
        config_path = Path.home() / ".pnlclaw" / "config.yaml"

    yaml_values = _load_yaml(config_path)
    global _yaml_values
    _yaml_values = yaml_values
    return PnLClawConfig(**overrides)
