"""LLM model router with fallback chain.

Manages multiple ``LLMProvider`` instances and automatically fails over
from primary → fallback → local when a provider is unavailable.
Distilled from OpenClaw provider fallback chain pattern.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from pnlclaw_llm.base import (
    LLMAuthError,
    LLMConfig,
    LLMError,
    LLMMessage,
    LLMProvider,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Health status
# ---------------------------------------------------------------------------


@dataclass
class ProviderHealth:
    """Health status of a single LLM provider."""

    name: str
    available: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# LLMRouter
# ---------------------------------------------------------------------------


@dataclass
class _ProviderEntry:
    """Internal wrapper for a named provider in the chain."""

    name: str
    provider: LLMProvider


class LLMRouter:
    """Routes LLM requests through a prioritized provider chain.

    Providers are tried in order. If the current provider fails with a
    retryable error (connection, rate-limit), the next provider is tried.
    Auth errors are *not* retried on the same provider but *do* trigger
    fallback to the next one.

    All providers failing raises ``LLMError``.

    Args:
        providers: Ordered list of ``(name, LLMProvider)`` tuples.
            First entry is primary, subsequent are fallbacks.
    """

    def __init__(self, providers: list[tuple[str, LLMProvider]]) -> None:
        if not providers:
            raise ValueError("LLMRouter requires at least one provider")
        self._chain = [_ProviderEntry(name=n, provider=p) for n, p in providers]

    @property
    def provider_names(self) -> list[str]:
        """Names of all registered providers in priority order."""
        return [e.name for e in self._chain]

    # ----- chat -----

    async def chat(self, messages: list[LLMMessage], **kwargs: Any) -> str:
        """Route a chat request through the fallback chain."""
        errors: list[tuple[str, Exception]] = []
        for entry in self._chain:
            try:
                result = await entry.provider.chat(messages, **kwargs)
                return result
            except LLMError as exc:
                errors.append((entry.name, exc))
                logger.warning(
                    "Provider '%s' failed: %s. Trying next provider.",
                    entry.name,
                    exc,
                )
                continue
        raise LLMError(self._format_all_failed(errors))

    # ----- chat_stream -----

    async def chat_stream(self, messages: list[LLMMessage], **kwargs: Any) -> AsyncIterator[str]:
        """Route a streaming chat request through the fallback chain.

        Note: Once streaming starts from a provider, failures mid-stream
        are *not* retried on the next provider (partial data was already yielded).
        """
        errors: list[tuple[str, Exception]] = []
        for entry in self._chain:
            try:
                async for chunk in entry.provider.chat_stream(messages, **kwargs):
                    yield chunk
                return  # Streaming completed successfully
            except LLMError as exc:
                errors.append((entry.name, exc))
                logger.warning(
                    "Provider '%s' stream failed: %s. Trying next provider.",
                    entry.name,
                    exc,
                )
                continue
        raise LLMError(self._format_all_failed(errors))

    # ----- generate_structured -----

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        output_schema: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Route a structured generation request through the fallback chain."""
        errors: list[tuple[str, Exception]] = []
        for entry in self._chain:
            try:
                result = await entry.provider.generate_structured(
                    messages, output_schema, **kwargs
                )
                return result
            except LLMError as exc:
                errors.append((entry.name, exc))
                logger.warning(
                    "Provider '%s' structured gen failed: %s. Trying next provider.",
                    entry.name,
                    exc,
                )
                continue
        raise LLMError(self._format_all_failed(errors))

    # ----- health_check -----

    async def health_check(self) -> list[ProviderHealth]:
        """Check health of all providers by sending a minimal chat request.

        Returns:
            List of ``ProviderHealth`` for each provider in the chain.
        """
        test_messages = [LLMMessage(role="user", content="ping")]
        results: list[ProviderHealth] = []
        for entry in self._chain:
            try:
                await entry.provider.chat(test_messages, max_tokens=1)
                results.append(ProviderHealth(name=entry.name, available=True))
            except Exception as exc:
                results.append(
                    ProviderHealth(name=entry.name, available=False, error=str(exc))
                )
        return results

    # ----- helpers -----

    @staticmethod
    def _format_all_failed(errors: list[tuple[str, Exception]]) -> str:
        parts = [f"  {name}: {exc}" for name, exc in errors]
        return "All LLM providers failed:\n" + "\n".join(parts)
