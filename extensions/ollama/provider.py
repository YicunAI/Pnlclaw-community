"""Ollama extension: thin wrapper around the first-party Ollama provider."""

from __future__ import annotations

from pnlclaw_llm.ollama import OllamaProvider


class OllamaExtensionProvider(OllamaProvider):
    """LLM provider registered by the Ollama extension plugin.

    Defaults ``base_url`` to ``http://localhost:11434`` via the wrapped
    :class:`OllamaProvider` when unset.
    """
