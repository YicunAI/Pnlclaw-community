"""LLM provider abstraction: ABC, message types, config, and exceptions."""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Base exception for all LLM-related errors."""


class LLMConnectionError(LLMError):
    """Failed to connect to the LLM provider (network / 5xx)."""


class LLMRateLimitError(LLMError):
    """Provider returned a rate-limit response (429)."""

    def __init__(
        self, message: str = "Rate limit exceeded", retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMAuthError(LLMError):
    """Authentication or authorization failure (401 / 403)."""


class LLMContextLengthError(LLMError):
    """Request exceeded the model's context window limit (400)."""


# ---------------------------------------------------------------------------
# LLMMessage
# ---------------------------------------------------------------------------


class LLMRole(str, Enum):
    """Roles for LLM chat messages."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMMessage(BaseModel):
    """Single message in an LLM conversation."""

    role: LLMRole = Field(..., description="Message role")
    content: str = Field(..., description="Message text content")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"role": "user", "content": "Analyze BTC/USDT trend"},
                {"role": "system", "content": "You are a quant analyst."},
            ]
        }
    )


# ---------------------------------------------------------------------------
# LLMConfig
# ---------------------------------------------------------------------------


class LLMConfig(BaseModel):
    """Configuration for an LLM provider instance."""

    model: str = Field(..., description="Model identifier, e.g. 'gpt-4o', 'deepseek-chat'")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(4096, gt=0, description="Maximum tokens in response")
    api_key: str | None = Field(None, description="API key (prefer env var over hardcoding)")
    base_url: str | None = Field(None, description="Custom API base URL for compatible providers")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "model": "gpt-4o",
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "api_key": None,
                    "base_url": None,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# LLMProvider ABC
# ---------------------------------------------------------------------------


class LLMProvider(abc.ABC):
    """Abstract base class for LLM providers.

    All providers must implement three core methods:

    - ``chat``: Single-turn or multi-turn conversation returning a complete response.
    - ``chat_stream``: Streaming variant yielding text chunks.
    - ``generate_structured``: Constrained generation returning parsed JSON dict.

    Optional method (v0.1.1):

    - ``chat_with_tools``: Native function calling (tool use). Providers that
      support it should override; default falls back to ``chat()``.

    Implementations should raise the appropriate ``LLMError`` subclass on failure.
    """

    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    @property
    def config(self) -> LLMConfig:
        """Current provider configuration."""
        return self._config

    @abc.abstractmethod
    async def chat(self, messages: list[LLMMessage], **kwargs: Any) -> str:
        """Send messages and return the complete assistant response.

        Args:
            messages: Conversation history.
            **kwargs: Provider-specific overrides (temperature, max_tokens, etc.).

        Returns:
            The assistant's response text.

        Raises:
            LLMError: On any LLM-related failure.
        """

    @abc.abstractmethod
    async def chat_stream(self, messages: list[LLMMessage], **kwargs: Any) -> AsyncIterator[str]:
        """Send messages and yield streaming text chunks.

        Args:
            messages: Conversation history.
            **kwargs: Provider-specific overrides.

        Yields:
            Text chunks as they arrive.

        Raises:
            LLMError: On any LLM-related failure.
        """
        # Make this a proper async generator for type-checking purposes
        yield ""  # pragma: no cover
        raise NotImplementedError  # pragma: no cover

    async def chat_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> "ToolCallResult":
        """Native function calling (tool use).

        Providers that support native tool calling should override this method.
        Default implementation falls back to ``chat()`` and returns the text
        response as a ``ToolCallResult`` with no tool calls.

        Args:
            messages: Conversation history.
            tools: Tool definitions in OpenAI function calling format.
            **kwargs: Provider-specific overrides.

        Returns:
            Structured ``ToolCallResult`` containing tool calls and/or text.
        """
        from pnlclaw_llm.schemas import ToolCallResult

        response = await self.chat(messages, **kwargs)
        return ToolCallResult(text=response)

    @abc.abstractmethod
    async def generate_structured(
        self,
        messages: list[LLMMessage],
        output_schema: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a response constrained to a JSON schema.

        Args:
            messages: Conversation history.
            output_schema: JSON Schema describing the expected output structure.
            **kwargs: Provider-specific overrides.

        Returns:
            Parsed JSON dict conforming to *output_schema*.

        Raises:
            LLMError: On any LLM-related failure (including parse failures).
        """
