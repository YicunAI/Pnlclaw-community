"""Shared CLI constants."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".pnlclaw" / "config.yaml"
DEFAULT_DATA_DIR = Path.home() / ".pnlclaw" / "data"
DEFAULT_DB_PATH = Path.home() / ".pnlclaw" / "data" / "pnlclaw.db"
DEFAULT_LOG_DIR = Path.home() / ".pnlclaw" / "logs"
SCHEMA_VERSION = "0.1"


def cli_version() -> str:
    try:
        return importlib.metadata.version("pnlclaw-cli")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"
