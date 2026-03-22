"""Tests for pnlclaw_llm.ollama — Ollama local provider."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from pnlclaw_llm.base import (
    LLMConfig,
    LLMConnectionError,
    LLMError,
    LLMMessage,
    LLMRole,
)
from pnlclaw_llm.ollama import OllamaProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ollama_response(content: str = "hello", done: bool = True) -> dict[str, Any]:
    return {"message": {"role": "assistant", "content": content}, "done": done}


def _make_provider(
    model: str = "llama3",
    client: httpx.AsyncClient | None = None,
) -> OllamaProvider:
    return OllamaProvider(
        config=LLMConfig(model=model),
        client=client,
    )


# ---------------------------------------------------------------------------
# chat tests
# ---------------------------------------------------------------------------


class TestOllamaChat:
    @pytest.mark.asyncio
    async def test_successful_chat(self) -> None:
        mock_resp = httpx.Response(200, json=_make_ollama_response("test reply"))
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        result = await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])
        assert result == "test reply"

    @pytest.mark.asyncio
    async def test_connection_error_gives_clear_message(self) -> None:
        def raise_connect(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(raise_connect)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        with pytest.raises(LLMConnectionError, match="Ollama"):
            await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])

    @pytest.mark.asyncio
    async def test_server_error(self) -> None:
        mock_resp = httpx.Response(500, text="model not found")
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        with pytest.raises(LLMError, match="500"):
            await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])

    @pytest.mark.asyncio
    async def test_payload_format(self) -> None:
        captured: list[dict[str, Any]] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(json.loads(req.content))
            return httpx.Response(200, json=_make_ollama_response("ok"))

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(model="llama3", client=client)
        await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])

        payload = captured[0]
        assert payload["model"] == "llama3"
        assert payload["stream"] is False
        assert "options" in payload
        assert "temperature" in payload["options"]

    @pytest.mark.asyncio
    async def test_uses_correct_url(self) -> None:
        captured_urls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured_urls.append(str(req.url))
            return httpx.Response(200, json=_make_ollama_response("ok"))

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])
        assert "/api/chat" in captured_urls[0]
        assert "localhost:11434" in captured_urls[0]


# ---------------------------------------------------------------------------
# chat_stream tests
# ---------------------------------------------------------------------------


class TestOllamaStream:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self) -> None:
        lines = "\n".join([
            json.dumps({"message": {"content": "Hello"}, "done": False}),
            json.dumps({"message": {"content": " World"}, "done": True}),
        ])
        mock_resp = httpx.Response(200, content=lines.encode())
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        chunks: list[str] = []
        async for chunk in provider.chat_stream([LLMMessage(role=LLMRole.USER, content="hi")]):
            chunks.append(chunk)
        assert "".join(chunks) == "Hello World"

    @pytest.mark.asyncio
    async def test_stream_connection_error(self) -> None:
        def raise_connect(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(raise_connect)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        with pytest.raises(LLMConnectionError, match="Ollama"):
            async for _ in provider.chat_stream([LLMMessage(role=LLMRole.USER, content="hi")]):
                pass


# ---------------------------------------------------------------------------
# generate_structured tests
# ---------------------------------------------------------------------------


class TestOllamaStructured:
    @pytest.mark.asyncio
    async def test_returns_parsed_json(self) -> None:
        mock_resp = httpx.Response(
            200,
            json=_make_ollama_response('{"action": "buy", "symbol": "BTC/USDT"}'),
        )
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        result = await provider.generate_structured(
            [LLMMessage(role=LLMRole.USER, content="trade")],
            output_schema={"type": "object"},
        )
        assert result == {"action": "buy", "symbol": "BTC/USDT"}

    @pytest.mark.asyncio
    async def test_format_json_in_payload(self) -> None:
        captured: list[dict[str, Any]] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(json.loads(req.content))
            return httpx.Response(200, json=_make_ollama_response('{"ok": true}'))

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        await provider.generate_structured(
            [LLMMessage(role=LLMRole.USER, content="hi")],
            output_schema={"type": "object"},
        )
        assert captured[0]["format"] == "json"

    @pytest.mark.asyncio
    async def test_invalid_json_raises_error(self) -> None:
        mock_resp = httpx.Response(
            200,
            json=_make_ollama_response("not json at all"),
        )
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        with pytest.raises(LLMError, match="Failed to parse"):
            await provider.generate_structured(
                [LLMMessage(role=LLMRole.USER, content="hi")],
                output_schema={"type": "object"},
            )
