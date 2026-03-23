"""OpenAI extension: thin wrapper around the first-party OpenAI-compatible provider."""

from __future__ import annotations

from pnlclaw_llm.openai_compat import OpenAICompatProvider


class OpenAIExtensionProvider(OpenAICompatProvider):
    """LLM provider registered by the OpenAI extension plugin.

    Delegates to :class:`OpenAICompatProvider`. API keys and ``base_url``
    must come from environment or app configuration—never from chat.
    """
