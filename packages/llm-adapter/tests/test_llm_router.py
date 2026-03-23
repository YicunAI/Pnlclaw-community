"""Tests for pnlclaw_llm.router — LLM model router with fallback chain."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

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
from pnlclaw_llm.router import LLMRouter

# ---------------------------------------------------------------------------
# Stub providers
# ---------------------------------------------------------------------------


class SuccessProvider(LLMProvider):
    """Always succeeds with a configurable response."""

    def __init__(self, response: str = "ok") -> None:
        super().__init__(config=LLMConfig(model="stub"))
        self._response = response

    async def chat(self, messages: list[LLMMessage], **kwargs: Any) -> str:
        return self._response

    async def chat_stream(self, messages: list[LLMMessage], **kwargs: Any) -> AsyncIterator[str]:
        for word in self._response.split():
            yield word

    async def generate_structured(
        self, messages: list[LLMMessage], output_schema: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        return {"result": self._response}


class FailProvider(LLMProvider):
    """Always raises the given exception."""

    def __init__(self, exc: LLMError) -> None:
        super().__init__(config=LLMConfig(model="fail"))
        self._exc = exc

    async def chat(self, messages: list[LLMMessage], **kwargs: Any) -> str:
        raise self._exc

    async def chat_stream(self, messages: list[LLMMessage], **kwargs: Any) -> AsyncIterator[str]:
        raise self._exc
        yield ""  # type: ignore[misc]  # Make it an async generator

    async def generate_structured(
        self, messages: list[LLMMessage], output_schema: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        raise self._exc


MSG = [LLMMessage(role=LLMRole.USER, content="test")]


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_requires_at_least_one_provider(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            LLMRouter([])

    def test_provider_names(self) -> None:
        router = LLMRouter(
            [
                ("primary", SuccessProvider("a")),
                ("fallback", SuccessProvider("b")),
            ]
        )
        assert router.provider_names == ["primary", "fallback"]


# ---------------------------------------------------------------------------
# Chat fallback tests
# ---------------------------------------------------------------------------


class TestChatFallback:
    @pytest.mark.asyncio
    async def test_primary_success(self) -> None:
        router = LLMRouter(
            [
                ("primary", SuccessProvider("primary_response")),
                ("fallback", SuccessProvider("fallback_response")),
            ]
        )
        result = await router.chat(MSG)
        assert result == "primary_response"

    @pytest.mark.asyncio
    async def test_fallback_on_connection_error(self) -> None:
        router = LLMRouter(
            [
                ("primary", FailProvider(LLMConnectionError("down"))),
                ("fallback", SuccessProvider("fallback_response")),
            ]
        )
        result = await router.chat(MSG)
        assert result == "fallback_response"

    @pytest.mark.asyncio
    async def test_fallback_on_rate_limit(self) -> None:
        router = LLMRouter(
            [
                ("primary", FailProvider(LLMRateLimitError("429"))),
                ("fallback", SuccessProvider("fallback_response")),
            ]
        )
        result = await router.chat(MSG)
        assert result == "fallback_response"

    @pytest.mark.asyncio
    async def test_fallback_on_auth_error(self) -> None:
        router = LLMRouter(
            [
                ("primary", FailProvider(LLMAuthError("bad key"))),
                ("fallback", SuccessProvider("fallback_response")),
            ]
        )
        result = await router.chat(MSG)
        assert result == "fallback_response"

    @pytest.mark.asyncio
    async def test_all_fail_raises_error(self) -> None:
        router = LLMRouter(
            [
                ("primary", FailProvider(LLMConnectionError("down"))),
                ("fallback", FailProvider(LLMAuthError("bad key"))),
            ]
        )
        with pytest.raises(LLMError, match="All LLM providers failed"):
            await router.chat(MSG)

    @pytest.mark.asyncio
    async def test_three_level_chain(self) -> None:
        router = LLMRouter(
            [
                ("openai", FailProvider(LLMConnectionError("timeout"))),
                ("deepseek", FailProvider(LLMRateLimitError("429"))),
                ("ollama", SuccessProvider("local_response")),
            ]
        )
        result = await router.chat(MSG)
        assert result == "local_response"


# ---------------------------------------------------------------------------
# Stream fallback tests
# ---------------------------------------------------------------------------


class TestStreamFallback:
    @pytest.mark.asyncio
    async def test_stream_primary_success(self) -> None:
        router = LLMRouter(
            [
                ("primary", SuccessProvider("hello world")),
            ]
        )
        chunks: list[str] = []
        async for chunk in router.chat_stream(MSG):
            chunks.append(chunk)
        assert chunks == ["hello", "world"]

    @pytest.mark.asyncio
    async def test_stream_fallback_on_error(self) -> None:
        router = LLMRouter(
            [
                ("primary", FailProvider(LLMConnectionError("down"))),
                ("fallback", SuccessProvider("fallback ok")),
            ]
        )
        chunks: list[str] = []
        async for chunk in router.chat_stream(MSG):
            chunks.append(chunk)
        assert chunks == ["fallback", "ok"]


# ---------------------------------------------------------------------------
# Structured generation fallback tests
# ---------------------------------------------------------------------------


class TestStructuredFallback:
    @pytest.mark.asyncio
    async def test_structured_primary_success(self) -> None:
        router = LLMRouter(
            [
                ("primary", SuccessProvider("ok")),
            ]
        )
        result = await router.generate_structured(MSG, {"type": "object"})
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_structured_fallback_on_error(self) -> None:
        router = LLMRouter(
            [
                ("primary", FailProvider(LLMConnectionError("down"))),
                ("fallback", SuccessProvider("fallback")),
            ]
        )
        result = await router.generate_structured(MSG, {"type": "object"})
        assert result == {"result": "fallback"}


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_all_healthy(self) -> None:
        router = LLMRouter(
            [
                ("primary", SuccessProvider("ok")),
                ("fallback", SuccessProvider("ok")),
            ]
        )
        results = await router.health_check()
        assert len(results) == 2
        assert all(r.available for r in results)

    @pytest.mark.asyncio
    async def test_mixed_health(self) -> None:
        router = LLMRouter(
            [
                ("primary", FailProvider(LLMConnectionError("down"))),
                ("fallback", SuccessProvider("ok")),
            ]
        )
        results = await router.health_check()
        assert results[0].available is False
        assert results[0].error is not None
        assert results[1].available is True
        assert results[1].error is None
