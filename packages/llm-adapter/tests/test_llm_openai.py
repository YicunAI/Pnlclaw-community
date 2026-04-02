"""Tests for pnlclaw_llm.openai_compat — OpenAI-compatible provider."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from pnlclaw_llm.base import (
    LLMAuthError,
    LLMConfig,
    LLMConnectionError,
    LLMError,
    LLMMessage,
    LLMRateLimitError,
    LLMRole,
)
from pnlclaw_llm.openai_compat import OpenAICompatProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chat_response(content: str = "hello") -> dict[str, Any]:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _make_provider(
    model: str = "gpt-4o",
    api_key: str = "sk-test",
    base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        config=LLMConfig(model=model, api_key=api_key, base_url=base_url),
        client=client,
    )


# ---------------------------------------------------------------------------
# chat tests
# ---------------------------------------------------------------------------


class TestChat:
    @pytest.mark.asyncio
    async def test_successful_chat(self) -> None:
        mock_resp = httpx.Response(200, json=_make_chat_response("test reply"))
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        result = await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])
        assert result == "test reply"

    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self) -> None:
        mock_resp = httpx.Response(401, text="Unauthorized")
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        with pytest.raises(LLMAuthError):
            await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])

    @pytest.mark.asyncio
    async def test_403_raises_auth_error(self) -> None:
        mock_resp = httpx.Response(403, text="Forbidden")
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        with pytest.raises(LLMAuthError):
            await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self) -> None:
        mock_resp = httpx.Response(429, text="Too Many Requests")
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        with pytest.raises(LLMRateLimitError):
            await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])

    @pytest.mark.asyncio
    async def test_500_raises_connection_error(self) -> None:
        mock_resp = httpx.Response(500, text="Internal Server Error")
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        with pytest.raises(LLMConnectionError):
            await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])

    @pytest.mark.asyncio
    async def test_empty_choices_raises_error(self) -> None:
        mock_resp = httpx.Response(200, json={"choices": []})
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        with pytest.raises(LLMError, match="Empty choices"):
            await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])

    @pytest.mark.asyncio
    async def test_custom_base_url(self) -> None:
        """Verify the request goes to the custom base URL."""
        captured_urls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured_urls.append(str(req.url))
            return httpx.Response(200, json=_make_chat_response("ok"))

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(
            base_url="https://api.deepseek.com/v1",
            client=client,
        )
        await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])
        assert "api.deepseek.com" in captured_urls[0]

    @pytest.mark.asyncio
    async def test_payload_includes_model_and_params(self) -> None:
        captured_payloads: list[dict[str, Any]] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured_payloads.append(json.loads(req.content))
            return httpx.Response(200, json=_make_chat_response("ok"))

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(model="deepseek-chat", client=client)
        await provider.chat(
            [LLMMessage(role=LLMRole.USER, content="hi")],
            temperature=0.1,
        )
        payload = captured_payloads[0]
        assert payload["model"] == "deepseek-chat"
        assert payload["temperature"] == 0.1
        assert payload["stream"] is False


# ---------------------------------------------------------------------------
# chat_stream tests
# ---------------------------------------------------------------------------


class TestChatStream:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self) -> None:
        sse_lines = (
            'data: {"choices":[{"delta":{"content":"Hello"}}]}\n'
            "\n"
            'data: {"choices":[{"delta":{"content":" World"}}]}\n'
            "\n"
            "data: [DONE]\n"
        )
        mock_resp = httpx.Response(200, content=sse_lines.encode(), headers={"content-type": "text/event-stream"})

        async def mock_stream(method, url, **kwargs):  # type: ignore[no-untyped-def]
            return mock_resp

        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        chunks: list[str] = []
        async for chunk in provider.chat_stream([LLMMessage(role=LLMRole.USER, content="hi")]):
            chunks.append(chunk)
        assert "".join(chunks) == "Hello World"

    @pytest.mark.asyncio
    async def test_stream_handles_empty_delta(self) -> None:
        sse_lines = (
            'data: {"choices":[{"delta":{}}]}\n\ndata: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n'
        )
        mock_resp = httpx.Response(200, content=sse_lines.encode())
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        chunks: list[str] = []
        async for chunk in provider.chat_stream([LLMMessage(role=LLMRole.USER, content="hi")]):
            chunks.append(chunk)
        assert chunks == ["ok"]


# ---------------------------------------------------------------------------
# generate_structured tests
# ---------------------------------------------------------------------------


class TestGenerateStructured:
    @pytest.mark.asyncio
    async def test_returns_parsed_json(self) -> None:
        mock_resp = httpx.Response(
            200,
            json=_make_chat_response('{"symbol": "BTC/USDT", "side": "buy"}'),
        )
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        result = await provider.generate_structured(
            [LLMMessage(role=LLMRole.USER, content="trade intent")],
            output_schema={"type": "object"},
        )
        assert result == {"symbol": "BTC/USDT", "side": "buy"}

    @pytest.mark.asyncio
    async def test_invalid_json_raises_error(self) -> None:
        mock_resp = httpx.Response(
            200,
            json=_make_chat_response("not valid json {{{"),
        )
        transport = httpx.MockTransport(lambda req: mock_resp)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        with pytest.raises(LLMError, match="Failed to parse"):
            await provider.generate_structured(
                [LLMMessage(role=LLMRole.USER, content="trade")],
                output_schema={"type": "object"},
            )

    @pytest.mark.asyncio
    async def test_payload_has_response_format(self) -> None:
        captured: list[dict[str, Any]] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(json.loads(req.content))
            return httpx.Response(200, json=_make_chat_response('{"ok": true}'))

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        await provider.generate_structured(
            [LLMMessage(role=LLMRole.USER, content="hi")],
            output_schema={"type": "object"},
        )
        assert captured[0]["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_fallback_without_response_format_on_400(self) -> None:
        requests: list[dict[str, Any]] = []

        def handler(req: httpx.Request) -> httpx.Response:
            payload = json.loads(req.content)
            requests.append(payload)
            if len(requests) == 1:
                return httpx.Response(400, text="response_format unsupported")
            return httpx.Response(200, json=_make_chat_response('{"ok": true}'))

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        result = await provider.generate_structured(
            [LLMMessage(role=LLMRole.USER, content="hi")],
            output_schema={"type": "object"},
        )
        assert result == {"ok": True}
        assert requests[0]["response_format"] == {"type": "json_object"}
        assert "response_format" not in requests[1]


# ---------------------------------------------------------------------------
# Error classification helper tests
# ---------------------------------------------------------------------------


class TestErrorClassification:
    @pytest.mark.asyncio
    async def test_connection_error_wrapped(self) -> None:
        def raise_connect(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(raise_connect)
        client = httpx.AsyncClient(transport=transport)

        provider = _make_provider(client=client)
        with pytest.raises(LLMConnectionError):
            await provider.chat([LLMMessage(role=LLMRole.USER, content="hi")])
