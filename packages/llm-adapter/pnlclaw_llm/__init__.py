"""pnlclaw_llm -- LLM provider abstraction for PnLClaw.

Public API:

- ``LLMProvider``: Abstract base class for LLM providers.
- ``LLMConfig``: Provider configuration model.
- ``LLMMessage``, ``LLMRole``: Chat message types.
- ``LLMError``, ``LLMConnectionError``, ``LLMRateLimitError``, ``LLMAuthError``: Exceptions.
- ``OpenAICompatProvider``: OpenAI / DeepSeek / OpenRouter provider.
- ``OllamaProvider``: Local Ollama provider.
- ``LLMRouter``: Multi-provider router with fallback chain.
- ``get_json_schema``, ``extract_structured``: Structured output helpers.
"""

from pnlclaw_llm.base import (
    LLMAuthError,
    LLMConfig,
    LLMConnectionError,
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMRateLimitError,
    LLMRole,
)
from pnlclaw_llm.ollama import OllamaProvider
from pnlclaw_llm.openai_compat import OpenAICompatProvider
from pnlclaw_llm.router import LLMRouter
from pnlclaw_llm.schemas import (
    MarketAnalysis,
    extract_structured,
    get_json_schema,
    market_analysis_schema,
    strategy_config_schema,
    trade_intent_schema,
)

__all__ = [
    "LLMAuthError",
    "LLMConfig",
    "LLMConnectionError",
    "LLMError",
    "LLMMessage",
    "LLMProvider",
    "LLMRateLimitError",
    "LLMRole",
    "LLMRouter",
    "OllamaProvider",
    "OpenAICompatProvider",
    "MarketAnalysis",
    "extract_structured",
    "get_json_schema",
    "trade_intent_schema",
    "strategy_config_schema",
    "market_analysis_schema",
]
