from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pnlclaw_core.infra.atomic_write import atomic_write
from pnlclaw_security.secrets import SecretManager, SecretRef, SecretSource

from app.core.crypto import KeyPairManager, decrypt_if_encrypted

logger = logging.getLogger(__name__)


class SettingsService:
    """Persist non-sensitive settings and handle secret state in keyring."""

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        secret_manager: SecretManager | None = None,
        key_pair_manager: KeyPairManager | None = None,
    ) -> None:
        self._config_path = config_path or (Path.home() / ".pnlclaw" / "settings.json")
        self._secret_manager = secret_manager or SecretManager()
        self._key_pair_manager = key_pair_manager

    async def get_settings(self) -> dict[str, Any]:
        settings = self._load_non_sensitive()

        exchange_key = await self._secret_manager.exists(
            SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.exchange", id="api_key")
        )
        exchange_secret = await self._secret_manager.exists(
            SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.exchange", id="api_secret")
        )
        llm_key = await self._secret_manager.exists(
            SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.llm", id="api_key")
        )

        settings["exchange"]["api_key_configured"] = exchange_key
        settings["exchange"]["api_secret_configured"] = exchange_secret
        settings["exchange"]["api_key_masked"] = "••••••••" if exchange_key else ""
        settings["exchange"]["api_secret_masked"] = "••••••••" if exchange_secret else ""

        settings["llm"]["api_key_configured"] = llm_key
        settings["llm"]["api_key_masked"] = "••••••••" if llm_key else ""

        settings["security"] = {
            "secret_backend": "keyring",
            "keyring_available": self._secret_manager.keyring_available(),
            "persistence_guarantee": "best-effort-os-keychain",
            "security_note": (
                "Secrets are stored via OS keychain when available. "
                "No software can guarantee absolute unbreakability."
            ),
        }

        return settings

    async def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        non_sensitive = self._load_non_sensitive()

        if "general" in payload and isinstance(payload["general"], dict):
            non_sensitive["general"].update(
                {
                    k: str(v)
                    for k, v in payload["general"].items()
                    if k in {"api_url", "default_symbol", "default_interval"}
                }
            )

        if "exchange" in payload and isinstance(payload["exchange"], dict):
            exchange = payload["exchange"]
            if "provider" in exchange:
                non_sensitive["exchange"]["provider"] = str(exchange["provider"])
            if "market_type" in exchange:
                non_sensitive["exchange"]["market_type"] = str(exchange["market_type"])

            await self._upsert_secret(
                SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.exchange", id="api_key"),
                value=exchange.get("api_key"),
                clear=bool(exchange.get("clear_api_key", False)),
            )
            await self._upsert_secret(
                SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.exchange", id="api_secret"),
                value=exchange.get("api_secret"),
                clear=bool(exchange.get("clear_api_secret", False)),
            )

        if "llm" in payload and isinstance(payload["llm"], dict):
            llm = payload["llm"]
            for key in ("provider", "base_url", "model"):
                if key in llm:
                    non_sensitive["llm"][key] = str(llm[key])

            if "smart_mode" in llm:
                non_sensitive["llm"]["smart_mode"] = bool(llm["smart_mode"])

            if "smart_models" in llm and isinstance(llm["smart_models"], dict):
                non_sensitive["llm"]["smart_models"] = {
                    str(k): str(v) for k, v in llm["smart_models"].items()
                    if k in ("strategy", "analysis", "quick")
                }

            await self._upsert_secret(
                SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.llm", id="api_key"),
                value=llm.get("api_key"),
                clear=bool(llm.get("clear_api_key", False)),
            )

        if "risk" in payload and isinstance(payload["risk"], dict):
            non_sensitive["risk"].update(
                {
                    k: str(v)
                    for k, v in payload["risk"].items()
                    if k in {"max_position_pct", "single_risk_pct", "daily_loss_limit_pct", "cooldown_seconds"}
                }
            )

        if "network" in payload and isinstance(payload["network"], dict):
            network = payload["network"]
            if "proxy_url" in network:
                non_sensitive["network"]["proxy_url"] = str(network["proxy_url"]).strip()

        if "skills" in payload and isinstance(payload["skills"], dict):
            skills = payload["skills"]
            if "extra_dirs" in skills and isinstance(skills["extra_dirs"], list):
                non_sensitive["skills"]["extra_dirs"] = [
                    str(d).strip() for d in skills["extra_dirs"] if str(d).strip()
                ]
            if "enabled" in skills and isinstance(skills["enabled"], dict):
                non_sensitive["skills"]["enabled"].update(
                    {str(k): bool(v) for k, v in skills["enabled"].items()}
                )

        if "ai" in payload and isinstance(payload["ai"], dict):
            ai_cfg = payload["ai"]
            _AI_BOOL_KEYS = ("react_enabled", "show_thinking", "hallucination_check")
            for key in _AI_BOOL_KEYS:
                if key in ai_cfg:
                    non_sensitive["ai"][key] = bool(ai_cfg[key])
            if "max_tool_rounds" in ai_cfg:
                non_sensitive["ai"]["max_tool_rounds"] = max(1, int(ai_cfg["max_tool_rounds"]))
            if "compaction_threshold" in ai_cfg:
                val = float(ai_cfg["compaction_threshold"])
                non_sensitive["ai"]["compaction_threshold"] = max(0.1, min(1.0, val))

        self._save_non_sensitive(non_sensitive)
        return await self.get_settings()

    async def _upsert_secret(self, ref: SecretRef, *, value: Any, clear: bool) -> None:
        if clear:
            await self._secret_manager.delete(ref)
            return

        if isinstance(value, str):
            candidate = value.strip()
            if candidate and candidate != "••••••••":
                try:
                    plaintext = decrypt_if_encrypted(self._key_pair_manager, candidate)
                except ValueError:
                    logger.warning("Failed to decrypt secret for %s — storing as-is", ref.id)
                    plaintext = candidate
                await self._secret_manager.store(ref, plaintext)

    def _load_non_sensitive(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "general": {
                "api_url": "http://localhost:8080",
                "default_symbol": "BTC/USDT",
                "default_interval": "1h",
            },
            "exchange": {
                "provider": "binance",
                "market_type": "spot",
            },
            "llm": {
                "provider": "openai",
                "base_url": "",
                "model": "",
                "smart_mode": False,
                "smart_models": {
                    "strategy": "",
                    "analysis": "",
                    "quick": "",
                },
            },
            "risk": {
                "max_position_pct": "10",
                "single_risk_pct": "2",
                "daily_loss_limit_pct": "5",
                "cooldown_seconds": "300",
            },
            "network": {
                "proxy_url": "",
            },
            "skills": {
                "extra_dirs": [],
                "enabled": {},
            },
            "ai": {
                "react_enabled": True,
                "max_tool_rounds": 10,
                "show_thinking": True,
                "hallucination_check": True,
                "compaction_threshold": 0.8,
            },
        }

        if not self._config_path.exists():
            return defaults

        try:
            loaded = json.loads(self._config_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return defaults

        skills_data = loaded.get("skills")
        if isinstance(skills_data, dict):
            if isinstance(skills_data.get("extra_dirs"), list):
                defaults["skills"]["extra_dirs"] = skills_data["extra_dirs"]
            if isinstance(skills_data.get("enabled"), dict):
                defaults["skills"]["enabled"] = skills_data["enabled"]

        for section in ("general", "exchange", "risk", "network"):
            data = loaded.get(section)
            if isinstance(data, dict):
                defaults[section].update({k: str(v) for k, v in data.items()})

        llm_data = loaded.get("llm")
        if isinstance(llm_data, dict):
            for k, v in llm_data.items():
                if k == "smart_mode":
                    defaults["llm"]["smart_mode"] = bool(v) if not isinstance(v, str) else v.lower() == "true"
                elif k == "smart_models" and isinstance(v, dict):
                    defaults["llm"]["smart_models"] = {str(mk): str(mv) for mk, mv in v.items()}
                else:
                    defaults["llm"][k] = str(v) if not isinstance(v, (bool, dict, list)) else v

        ai_data = loaded.get("ai")
        if isinstance(ai_data, dict):
            for k in ("react_enabled", "show_thinking", "hallucination_check"):
                if k in ai_data:
                    defaults["ai"][k] = bool(ai_data[k])
            if "max_tool_rounds" in ai_data:
                defaults["ai"]["max_tool_rounds"] = int(ai_data["max_tool_rounds"])
            if "compaction_threshold" in ai_data:
                defaults["ai"]["compaction_threshold"] = float(ai_data["compaction_threshold"])

        return defaults

    def _save_non_sensitive(self, settings: dict[str, Any]) -> None:
        payload = {
            "general": settings["general"],
            "exchange": settings["exchange"],
            "llm": settings["llm"],
            "risk": settings["risk"],
            "network": settings["network"],
            "skills": settings.get("skills", {"extra_dirs": [], "enabled": {}}),
            "ai": settings.get("ai", {
                "react_enabled": True,
                "max_tool_rounds": 10,
                "show_thinking": True,
                "hallucination_check": True,
                "compaction_threshold": 0.8,
            }),
        }
        atomic_write(self._config_path, json.dumps(payload, ensure_ascii=False, indent=2))

    def get_skills_config(self) -> dict[str, Any]:
        """Return only the skills configuration section."""
        data = self._load_non_sensitive()
        return data.get("skills", {"extra_dirs": [], "enabled": {}})

    def get_ai_config(self) -> dict[str, Any]:
        """Return the AI configuration section (PRD supplement E)."""
        data = self._load_non_sensitive()
        return data.get("ai", {
            "react_enabled": True,
            "max_tool_rounds": 10,
            "show_thinking": True,
            "hallucination_check": True,
            "compaction_threshold": 0.8,
        })

    def update_skills_config(self, skills_payload: dict[str, Any]) -> dict[str, Any]:
        """Update skills configuration and persist."""
        non_sensitive = self._load_non_sensitive()
        if "extra_dirs" in skills_payload and isinstance(skills_payload["extra_dirs"], list):
            non_sensitive["skills"]["extra_dirs"] = [
                str(d).strip() for d in skills_payload["extra_dirs"] if str(d).strip()
            ]
        if "enabled" in skills_payload and isinstance(skills_payload["enabled"], dict):
            non_sensitive["skills"]["enabled"].update(
                {str(k): bool(v) for k, v in skills_payload["enabled"].items()}
            )
        self._save_non_sensitive(non_sensitive)
        return non_sensitive["skills"]
