"""Ollama extension plugin entrypoint."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pnlclaw_core.plugin_sdk.api import PnLClawPluginAPI

from .provider import OllamaExtensionProvider

_MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"
MANIFEST: dict[str, Any] = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def setup(api: PnLClawPluginAPI) -> None:
    """Register the Ollama LLM provider."""
    api.register_llm_provider("ollama", OllamaExtensionProvider)
