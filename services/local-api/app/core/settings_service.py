from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pnlclaw_core.infra.atomic_write import atomic_write
from pnlclaw_security.secrets import SecretManager, SecretRef, SecretSource

from app.core.crypto import KeyPairManager, decrypt_if_encrypted

logger = logging.getLogger(__name__)

# Fields moved from settings.json into Keyring for privacy.
# These reveal which LLM service and proxy the user is using.
_LLM_KEYRING_FIELDS = ("base_url", "model", "provider")
_LLM_SMART_KEYRING_FIELDS = ("strategy", "analysis", "quick")


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
        settings["exchange"]["api_key_masked"] = "\u2022" * 8 if exchange_key else ""
        settings["exchange"]["api_secret_masked"] = "\u2022" * 8 if exchange_secret else ""

        settings["llm"]["api_key_configured"] = llm_key
        settings["llm"]["api_key_masked"] = "\u2022" * 8 if llm_key else ""

        # Restore keyring-stored LLM fields for the UI
        for field in _LLM_KEYRING_FIELDS:
            ref = SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.llm", id=field)
            try:
                resolved = await self._secret_manager.resolve(ref)
                settings["llm"][field] = resolved.use()
            except Exception:
                settings["llm"].setdefault(field, "")

        # Restore smart_models from keyring
        smart_models: dict[str, str] = {}
        for sm_field in _LLM_SMART_KEYRING_FIELDS:
            ref = SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.llm.smart", id=sm_field)
            try:
                resolved = await self._secret_manager.resolve(ref)
                smart_models[sm_field] = resolved.use()
            except Exception:
                smart_models[sm_field] = ""
        settings["llm"]["smart_models"] = smart_models

        # Restore proxy_url from keyring
        try:
            resolved = await self._secret_manager.resolve(
                SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.network", id="proxy_url")
            )
            settings["network"]["proxy_url"] = resolved.use()
        except Exception:
            settings["network"].setdefault("proxy_url", "")

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

            # Store provider-identifying fields in keyring, not settings.json
            for field in _LLM_KEYRING_FIELDS:
                if field in llm:
                    await self._upsert_secret(
                        SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.llm", id=field),
                        value=str(llm[field]),
                        clear=False,
                    )

            if "smart_mode" in llm:
                non_sensitive["llm"]["smart_mode"] = bool(llm["smart_mode"])

            if "smart_models" in llm and isinstance(llm["smart_models"], dict):
                for sm_field in _LLM_SMART_KEYRING_FIELDS:
                    if sm_field in llm["smart_models"]:
                        await self._upsert_secret(
                            SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.llm.smart", id=sm_field),
                            value=str(llm["smart_models"][sm_field]),
                            clear=False,
                        )

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
                # Store proxy_url in keyring — reveals network topology
                await self._upsert_secret(
                    SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.network", id="proxy_url"),
                    value=str(network["proxy_url"]).strip(),
                    clear=not str(network["proxy_url"]).strip(),
                )

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
            if "react_enabled" in ai_cfg:
                non_sensitive["ai"]["react_enabled"] = bool(ai_cfg["react_enabled"])
            if "show_thinking" in ai_cfg:
                non_sensitive["ai"]["show_thinking"] = bool(ai_cfg["show_thinking"])
            if "hallucination_check" in ai_cfg:
                non_sensitive["ai"]["hallucination_check"] = bool(ai_cfg["hallucination_check"])
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
            if candidate and candidate != "\u2022" * 8:
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
                # provider/base_url/model/smart_models now stored in keyring
                "smart_mode": False,
            },
            "risk": {
                "max_position_pct": "10",
                "single_risk_pct": "2",
                "daily_loss_limit_pct": "5",
                "cooldown_seconds": "300",
            },
            "network": {
                # proxy_url now stored in keyring
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
            logger.warning("Failed to load settings from %s, using defaults", self._config_path)
            return defaults

        # Deep merge loaded over defaults
        for section, section_defaults in defaults.items():
            if section in loaded and isinstance(loaded[section], dict) and isinstance(section_defaults, dict):
                merged = dict(section_defaults)
                merged.update(loaded[section])
                defaults[section] = merged
            elif section in loaded:
                defaults[section] = loaded[section]

        return defaults

    def _save_non_sensitive(self, data: dict[str, Any]) -> None:
        # Strip any sensitive fields that should not be persisted to disk
        safe = {}
        for section, values in data.items():
            if not isinstance(values, dict):
                safe[section] = values
                continue
            if section == "llm":
                # Only persist non-identifying flags
                safe[section] = {k: v for k, v in values.items() if k == "smart_mode"}
            elif section == "network":
                # proxy_url is in keyring; nothing to persist here
                safe[section] = {}
            else:
                safe[section] = values
        atomic_write(self._config_path, json.dumps(safe, ensure_ascii=False, indent=2))

    def get_llm_config(self) -> dict[str, Any]:
        """Return LLM config for internal use — not exposed via API."""
        data = self._load_non_sensitive()
        return data.get("llm", {})

    def get_mcp_config(self) -> dict[str, Any]:
        """Return only the MCP configuration section."""
        data = self._load_non_sensitive()
        return data.get("mcp", {"servers": {}})

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
