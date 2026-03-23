"""Auto-repair helpers for `pnlclaw doctor --repair`."""

from __future__ import annotations

import asyncio
import stat
import sys
from pathlib import Path

import yaml

from pnlclaw_cli.constants import SCHEMA_VERSION
from pnlclaw_storage.sqlite import DEFAULT_DB_PATH, AsyncSQLiteManager


def ensure_layout() -> None:
    root = Path.home() / ".pnlclaw"
    for sub in ("data", "logs", "paper", "secrets"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        try:
            root.chmod(stat.S_IRWXU)
        except OSError:
            pass


def write_default_config_if_missing() -> Path | None:
    root = Path.home() / ".pnlclaw"
    cfg_path = root / "config.yaml"
    if cfg_path.is_file():
        return None
    data = {
        "env": "development",
        "log_level": "INFO",
        "data_dir": str(root / "data").replace("\\", "/"),
        "db_path": str(DEFAULT_DB_PATH).replace("\\", "/"),
        "log_dir": str(root / "logs").replace("\\", "/"),
        "api_host": "127.0.0.1",
        "api_port": 8080,
        "default_exchange": "binance",
        "default_symbol": "BTCUSDT",
        "llm_provider": "openai_compatible",
        "llm_base_url": "",
        "llm_model": "",
        "llm_timeout_seconds": 60,
        "enable_real_trading": False,
        "paper_starting_balance": 10000.0,
    }
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    cfg_path.write_text(text, encoding="utf-8")
    return cfg_path


def init_sqlite() -> None:
    async def _go() -> None:
        mgr = AsyncSQLiteManager(DEFAULT_DB_PATH)
        await mgr.connect()
        await mgr.close()

    asyncio.run(_go())


def write_schema_sidecar() -> None:
    root = Path.home() / ".pnlclaw"
    root.mkdir(parents=True, exist_ok=True)
    (root / "schema_version").write_text(SCHEMA_VERSION + "\n", encoding="utf-8")


def run_standard_repairs() -> list[str]:
    """Apply safe repairs; return human-readable actions taken."""
    actions: list[str] = []
    ensure_layout()
    actions.append("Ensured ~/.pnlclaw directories exist")
    p = write_default_config_if_missing()
    if p:
        actions.append(f"Created default config at {p}")
    write_schema_sidecar()
    actions.append(f"Wrote schema sidecar ({SCHEMA_VERSION})")
    init_sqlite()
    actions.append(f"Initialized SQLite at {DEFAULT_DB_PATH}")
    return actions


def chmod_user_only_path(path: Path) -> None:
    if sys.platform == "win32":
        return
    try:
        path.chmod(stat.S_IRWXU)
    except OSError:
        pass


def chmod_secret_files() -> None:
    root = Path.home() / ".pnlclaw" / "secrets"
    if not root.is_dir():
        return
    for p in root.rglob("*"):
        if p.is_file():
            try:
                p.chmod(0o600)
            except OSError:
                pass
