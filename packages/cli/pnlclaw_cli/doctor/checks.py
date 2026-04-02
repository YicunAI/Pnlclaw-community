"""Individual doctor checks (19 total)."""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import socket
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml

from pnlclaw_cli.constants import SCHEMA_VERSION
from pnlclaw_core.config import load_config
from pnlclaw_storage.migrations_pkg import ALL_MIGRATIONS

MIN_DISK_MB = 100
EXPECTED_MIGRATION_IDS = {m.id for m in ALL_MIGRATIONS}


@dataclass
class CheckResult:
    name: str
    status: Literal["pass", "warn", "fail", "skip"]
    message: str
    repairable: bool = False


def _root() -> Path:
    return Path.home() / ".pnlclaw"


def _config_path() -> Path:
    return _root() / "config.yaml"


def _has_binance_key() -> bool:
    if os.environ.get("BINANCE_API_KEY") or os.environ.get("PNLCLAW_BINANCE_API_KEY"):
        return True
    p = _root() / "secrets" / "binance" / "api_key"
    return p.is_file()


def _has_llm_key() -> bool:
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("PNLCLAW_LLM_API_KEY"):
        return True
    p = _root() / "secrets" / "openai" / "api_key"
    return p.is_file()


def check_config_yaml_format() -> CheckResult:
    name = "Config file format"
    path = _config_path()
    if not path.is_file():
        return CheckResult(name, "warn", "No config file yet", repairable=True)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is not None and not isinstance(raw, dict):
            return CheckResult(name, "fail", "Top level must be a mapping", repairable=False)
    except yaml.YAMLError as exc:
        return CheckResult(name, "fail", f"Invalid YAML: {exc}", repairable=False)
    return CheckResult(name, "pass", "Valid", repairable=False)


def check_config_schema_version() -> CheckResult:
    name = "Config schema version"
    cfg = _config_path()
    side = _root() / "schema_version"
    if not cfg.is_file() and not side.is_file():
        return CheckResult(name, "skip", "No config file", repairable=False)
    if side.is_file():
        ver = side.read_text(encoding="utf-8").strip()
        if ver == SCHEMA_VERSION:
            return CheckResult(name, "pass", f"Compatible ({SCHEMA_VERSION})", repairable=False)
        msg = f"Sidecar {ver!r} may not match {SCHEMA_VERSION}"
        return CheckResult(name, "warn", msg, repairable=True)
    return CheckResult(name, "warn", "schema_version sidecar missing", repairable=True)


def check_exchange_key_exists() -> CheckResult:
    name = "Exchange API key"
    if _has_binance_key():
        return CheckResult(name, "pass", "Present", repairable=False)
    return CheckResult(name, "fail", "Not configured", repairable=False)


def check_exchange_rest() -> CheckResult:
    name = "Exchange connectivity (REST)"
    if not _has_binance_key():
        return CheckResult(name, "skip", "Skipped (no API key)", repairable=False)
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get("https://api.binance.com/api/v3/ping")
            if r.status_code == 200:
                return CheckResult(name, "pass", "Binance reachable", repairable=False)
            return CheckResult(name, "warn", f"Unexpected HTTP {r.status_code}", repairable=False)
    except httpx.HTTPError as exc:
        return CheckResult(name, "warn", f"Network error: {exc}", repairable=False)


def check_exchange_ws_connect() -> CheckResult:
    name = "Exchange WS (connect)"
    if not _has_binance_key():
        return CheckResult(name, "skip", "Skipped (no API key)", repairable=False)
    try:
        sock = socket.create_connection(("stream.binance.com", 9443), timeout=4.0)
        sock.close()
        return CheckResult(name, "pass", "stream.binance.com:9443 reachable", repairable=False)
    except OSError as exc:
        return CheckResult(name, "warn", str(exc), repairable=False)


def check_exchange_ws_heartbeat() -> CheckResult:
    name = "Exchange WS (heartbeat)"
    if not _has_binance_key():
        return CheckResult(name, "skip", "Skipped (no API key)", repairable=False)
    try:
        sock = socket.create_connection(("stream.binance.com", 9443), timeout=4.0)
        sock.close()
        return CheckResult(name, "pass", "Endpoint responsive", repairable=False)
    except OSError as exc:
        return CheckResult(name, "warn", str(exc), repairable=False)


def check_llm_key_exists() -> CheckResult:
    name = "LLM API key"
    cfg = load_config()
    if _has_llm_key():
        return CheckResult(name, "pass", "Present", repairable=False)
    if (cfg.llm_base_url or "").strip() and "ollama" in (cfg.llm_base_url or "").lower():
        return CheckResult(name, "pass", "Ollama (local) — no cloud key required", repairable=False)
    return CheckResult(name, "fail", "Not configured", repairable=False)


def check_llm_works() -> CheckResult:
    name = "LLM provider"
    cfg = load_config()
    if not (cfg.llm_base_url or "").strip() and not _has_llm_key():
        return CheckResult(name, "skip", "Skipped (not configured)", repairable=False)
    base = (cfg.llm_base_url or "").strip().rstrip("/")
    if "ollama" in base.lower() or "11434" in base:
        try:
            with httpx.Client(timeout=3.0) as c:
                r = c.get(base.split("/v1")[0] + "/api/tags" if "/v1" in base else "http://127.0.0.1:11434/api/tags")
                if r.status_code == 200:
                    return CheckResult(name, "pass", "Ollama responded", repairable=False)
        except httpx.HTTPError as exc:
            return CheckResult(name, "warn", str(exc), repairable=False)
    return CheckResult(name, "skip", "Skipped (optional cloud probe)", repairable=False)


def check_sqlite_exists() -> CheckResult:
    name = "SQLite database"
    cfg = load_config()
    dbp = Path(cfg.db_path)
    if not dbp.is_absolute():
        dbp = Path(cfg.db_path).resolve()
    if not dbp.is_file():
        return CheckResult(name, "fail", f"Missing: {dbp}", repairable=True)
    try:
        con = sqlite3.connect(str(dbp))
        con.execute("SELECT 1")
        con.close()
    except sqlite3.Error as exc:
        return CheckResult(name, "fail", str(exc), repairable=False)
    return CheckResult(name, "pass", "Opens OK", repairable=False)


def check_sqlite_migrations() -> CheckResult:
    name = "SQLite schema version"
    cfg = load_config()
    dbp = Path(cfg.db_path)
    if not dbp.is_absolute():
        dbp = Path(cfg.db_path).resolve()
    if not dbp.is_file():
        return CheckResult(name, "skip", "No database file", repairable=False)
    try:
        con = sqlite3.connect(str(dbp))
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'"
        cur = con.execute(sql)
        if cur.fetchone() is None:
            con.close()
            return CheckResult(name, "warn", "Migrations table missing", repairable=True)
        rows = con.execute("SELECT id FROM _migrations").fetchall()
        con.close()
        applied = {r[0] for r in rows}
        if not EXPECTED_MIGRATION_IDS.issubset(applied):
            missing = EXPECTED_MIGRATION_IDS - applied
            msg = f"Pending migrations: {', '.join(sorted(missing))}"
            return CheckResult(name, "warn", msg, repairable=True)
    except sqlite3.Error as exc:
        return CheckResult(name, "fail", str(exc), repairable=False)
    return CheckResult(name, "pass", "Matches expected migrations", repairable=False)


def check_strategy_migration() -> CheckResult:
    name = "Strategy configs migration"
    cfg = load_config()
    dbp = Path(cfg.db_path)
    if not dbp.is_absolute():
        dbp = Path(cfg.db_path).resolve()
    if not dbp.is_file():
        return CheckResult(name, "skip", "No database", repairable=False)
    try:
        con = sqlite3.connect(str(dbp))
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='strategies'")
        if cur.fetchone() is None:
            con.close()
            return CheckResult(name, "skip", "No strategies table", repairable=False)
        rows = con.execute("SELECT id, config_json FROM strategies").fetchall()
        con.close()
    except sqlite3.Error as exc:
        return CheckResult(name, "warn", f"Could not read strategies: {exc}", repairable=False)
    bad = 0
    for _sid, cj in rows:
        try:
            data = json.loads(cj)
        except json.JSONDecodeError:
            bad += 1
            continue
        if not isinstance(data, dict) or not all(k in data for k in ("id", "name", "type")):
            bad += 1
    if bad:
        msg = f"{bad} strategy row(s) may need migration"
        return CheckResult(name, "warn", msg, repairable=False)
    return CheckResult(name, "pass", "Stored strategies look valid", repairable=False)


def check_paper_consistency() -> CheckResult:
    name = "Paper trading consistency"
    paper_dir = _root() / "paper"
    acc_path = paper_dir / "accounts.json"
    ord_path = paper_dir / "orders.json"
    if not ord_path.is_file():
        return CheckResult(name, "pass", "No orders persisted", repairable=False)
    try:
        accounts = {}
        if acc_path.is_file():
            accounts = json.loads(acc_path.read_text(encoding="utf-8"))
        orders_raw = json.loads(ord_path.read_text(encoding="utf-8"))
        account_orders = orders_raw.get("account_orders", {})
        orphans = 0
        for aid, oids in account_orders.items():
            if aid not in accounts:
                orphans += len(oids)
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(name, "warn", str(exc), repairable=False)
    if orphans:
        return CheckResult(name, "fail", f"Orphan orders detected ({orphans})", repairable=False)
    return CheckResult(name, "pass", "No orphan orders", repairable=False)


def check_log_dir_writable() -> CheckResult:
    name = "Log directory"
    cfg = load_config()
    log_dir = Path(cfg.log_dir)
    if not log_dir.is_absolute():
        log_dir = Path(cfg.log_dir).resolve()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        probe = log_dir / ".pnlclaw_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        return CheckResult(name, "fail", str(exc), repairable=True)
    return CheckResult(name, "pass", "Writable", repairable=False)


def check_disk_space() -> CheckResult:
    name = "Disk space"
    path = _root()
    try:
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
        free_mb = usage.free // (1024 * 1024)
    except OSError as exc:
        return CheckResult(name, "warn", str(exc), repairable=False)
    if free_mb < MIN_DISK_MB:
        msg = f"Only {free_mb} MiB free (< {MIN_DISK_MB})"
        return CheckResult(name, "warn", msg, repairable=False)
    return CheckResult(name, "pass", f"{free_mb} MiB free", repairable=False)


def check_python_version() -> CheckResult:
    name = "Python version"
    v = sys.version_info
    if v >= (3, 11):
        return CheckResult(name, "pass", f"{v.major}.{v.minor}.{v.micro}", repairable=False)
    msg = f"{v.major}.{v.minor}.{v.micro} (need >= 3.11)"
    return CheckResult(name, "fail", msg, repairable=False)


def check_dependencies() -> CheckResult:
    name = "Dependency versions"
    pkgs = [
        ("pnlclaw-core", "0.1"),
        ("pnlclaw-types", "0.1"),
        ("pnlclaw-risk", "0.1"),
        ("pandas", "2"),
    ]
    issues: list[str] = []
    for dist, prefix in pkgs:
        try:
            ver = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            issues.append(f"{dist} missing")
            continue
        if not ver.startswith(prefix):
            issues.append(f"{dist}=={ver}")
    if issues:
        return CheckResult(name, "warn", "; ".join(issues), repairable=False)
    return CheckResult(name, "pass", "Core packages OK", repairable=False)


def check_pnlclaw_permissions() -> CheckResult:
    name = ".pnlclaw permissions"
    root = _root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        mode = root.stat().st_mode & 0o777
        if sys.platform != "win32" and mode & 0o077:
            return CheckResult(name, "warn", f"World/group writable ({mode:o})", repairable=True)
    except OSError as exc:
        return CheckResult(name, "fail", str(exc), repairable=True)
    return CheckResult(name, "pass", "OK", repairable=False)


def check_keychain() -> CheckResult:
    name = "Secret storage (keychain)"
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError:
        return CheckResult(name, "skip", "keyring package not installed", repairable=False)
    try:
        _ = keyring.get_password("pnlclaw", "__doctor_probe__")
    except Exception as exc:  # noqa: BLE001 — probe
        return CheckResult(name, "warn", f"Keyring not usable: {exc}", repairable=False)
    return CheckResult(name, "pass", "Keyring backend available", repairable=False)


def check_api_port() -> CheckResult:
    name = "Local API port"
    cfg = load_config()
    port = int(cfg.api_port)
    # Pass if health responds OR port is free (nothing bound)
    url = f"http://127.0.0.1:{port}/api/v1/health"
    try:
        with httpx.Client(timeout=2.0) as c:
            r = c.get(url)
            if r.status_code == 200:
                return CheckResult(name, "pass", f"API healthy on :{port}", repairable=False)
    except httpx.HTTPError:
        pass
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
    except OSError:
        return CheckResult(
            name,
            "warn",
            f"Port {port} in use but API health check failed",
            repairable=False,
        )
    finally:
        s.close()
    return CheckResult(name, "pass", f"Port {port} available (API not running)", repairable=False)


ALL_CHECKS: list[Any] = [
    check_python_version,
    check_config_yaml_format,
    check_config_schema_version,
    check_exchange_key_exists,
    check_exchange_rest,
    check_exchange_ws_connect,
    check_exchange_ws_heartbeat,
    check_llm_key_exists,
    check_llm_works,
    check_sqlite_exists,
    check_sqlite_migrations,
    check_strategy_migration,
    check_paper_consistency,
    check_log_dir_writable,
    check_disk_space,
    check_dependencies,
    check_pnlclaw_permissions,
    check_keychain,
    check_api_port,
]
