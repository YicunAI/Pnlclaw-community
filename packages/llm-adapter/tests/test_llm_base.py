"""Tests for pnlclaw_llm.base — LLMProvider ABC, types, and exceptions."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic import ValidationError

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

# ---------------------------------------------------------------------------
# Concrete stub for testing the ABC
# ---------------------------------------------------------------------------


class StubProvider(LLMProvider):
    """Minimal concrete implementation for testing."""

    async def chat(self, messages: list[LLMMessage], **kwargs: Any) -> str:
        return "stub response"

    async def chat_stream(self, messages: list[LLMMessage], **kwargs: Any) -> AsyncIterator[str]:
        for chunk in ["hello", " ", "world"]:
            yield chunk

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        output_schema: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {"result": "ok"}


# ---------------------------------------------------------------------------
# LLMMessage tests
# ---------------------------------------------------------------------------


class TestLLMMessage:
    def test_create(self) -> None:
        msg = LLMMessage(role=LLMRole.USER, content="hello")
        assert msg.role == LLMRole.USER
        assert msg.content == "hello"

    def test_serialization_roundtrip(self) -> None:
        msg = LLMMessage(role=LLMRole.SYSTEM, content="You are a quant.")
        data = json.loads(msg.model_dump_json())
        restored = LLMMessage.model_validate(data)
        assert restored == msg

    def test_all_roles(self) -> None:
        for role in LLMRole:
            msg = LLMMessage(role=role, content="test")
            assert msg.role == role


# ---------------------------------------------------------------------------
# LLMConfig tests
# ---------------------------------------------------------------------------


class TestLLMConfig:
    def test_defaults(self) -> None:
        cfg = LLMConfig(model="gpt-4o")
        assert cfg.temperature == 0.7
        assert cfg.max_tokens == 4096
        assert cfg.api_key is None
        assert cfg.base_url is None

    def test_custom_values(self) -> None:
        cfg = LLMConfig(
            model="deepseek-chat",
            temperature=0.3,
            max_tokens=2048,
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
        )
        assert cfg.model == "deepseek-chat"
        assert cfg.temperature == 0.3
        assert cfg.api_key == "sk-test"

    def test_serialization_roundtrip(self) -> None:
        cfg = LLMConfig(model="gpt-4o", api_key="sk-test")
        data = json.loads(cfg.model_dump_json())
        restored = LLMConfig.model_validate(data)
        assert restored == cfg

    def test_temperature_bounds(self) -> None:
        with pytest.raises(ValidationError):
            LLMConfig(model="m", temperature=-0.1)
        with pytest.raises(ValidationError):
            LLMConfig(model="m", temperature=2.1)


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_hierarchy(self) -> None:
        assert issubclass(LLMConnectionError, LLMError)
        assert issubclass(LLMRateLimitError, LLMError)
        assert issubclass(LLMAuthError, LLMError)

    def test_rate_limit_retry_after(self) -> None:
        err = LLMRateLimitError("too fast", retry_after=30.0)
        assert err.retry_after == 30.0
        assert "too fast" in str(err)

    def test_catch_all_via_base(self) -> None:
        for exc_cls in (LLMConnectionError, LLMRateLimitError, LLMAuthError):
            with pytest.raises(LLMError):
                raise exc_cls("test")


# ---------------------------------------------------------------------------
# Provider ABC tests
# ---------------------------------------------------------------------------


class TestLLMProviderABC:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            LLMProvider(config=LLMConfig(model="x"))  # type: ignore[abstract]

    @pytest.mark.asyncio
    async def test_stub_chat(self) -> None:
        provider = StubProvider(config=LLMConfig(model="stub"))
        result = await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])
        assert result == "stub response"

    @pytest.mark.asyncio
    async def test_stub_chat_stream(self) -> None:
        provider = StubProvider(config=LLMConfig(model="stub"))
        chunks: list[str] = []
        async for chunk in provider.chat_stream([LLMMessage(role=LLMRole.USER, content="hi")]):
            chunks.append(chunk)
        assert "".join(chunks) == "hello world"

    @pytest.mark.asyncio
    async def test_stub_generate_structured(self) -> None:
        provider = StubProvider(config=LLMConfig(model="stub"))
        result = await provider.generate_structured(
            [LLMMessage(role=LLMRole.USER, content="hi")],
            output_schema={"type": "object"},
        )
        assert result == {"result": "ok"}

    def test_config_accessible(self) -> None:
        cfg = LLMConfig(model="test-model")
        provider = StubProvider(config=cfg)
        assert provider.config is cfg
