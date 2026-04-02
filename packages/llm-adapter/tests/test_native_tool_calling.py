"""Tests for native function calling (tool use) across LLM providers.

Sprint 1.1 — Validates chat_with_tools() for OpenAI-compat, Ollama,
Router, and base class fallback paths.
"""

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
    LLMProvider,
    LLMRole,
)
from pnlclaw_llm.ollama import OllamaProvider
from pnlclaw_llm.openai_compat import OpenAICompatProvider
from pnlclaw_llm.router import LLMRouter
from pnlclaw_llm.schemas import ToolCallResult

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "market_ticker",
            "description": "Get the current price of a trading pair",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    }
]


def _make_tool_call_response(
    tool_calls: list[dict[str, Any]] | None = None,
    content: str | None = None,
    usage: dict[str, int] | None = None,
    model: str = "gpt-4o",
) -> dict[str, Any]:
    """Build an OpenAI-compatible chat completions response with tool_calls."""
    message: dict[str, Any] = {"role": "assistant"}
    if content is not None:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {
        "choices": [{"message": message, "finish_reason": "tool_calls" if tool_calls else "stop"}],
        "model": model,
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _make_openai_provider(client: httpx.AsyncClient) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        config=LLMConfig(model="gpt-4o", api_key="sk-test"),
        client=client,
    )


def _make_ollama_provider(client: httpx.AsyncClient) -> OllamaProvider:
    return OllamaProvider(
        config=LLMConfig(model="llama3", base_url="http://localhost:11434"),
        client=client,
    )


# ---------------------------------------------------------------------------
# Test 1: tools parameter correctly passed in payload
# ---------------------------------------------------------------------------


class TestToolsParameterPassing:
    @pytest.mark.asyncio
    async def test_openai_payload_includes_tools(self) -> None:
        captured: list[dict[str, Any]] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(json.loads(req.content))
            return httpx.Response(
                200,
                json=_make_tool_call_response(content="no tools needed"),
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        provider = _make_openai_provider(client)
        await provider.chat_with_tools(
            [LLMMessage(role=LLMRole.USER, content="price of BTC")],
            tools=SAMPLE_TOOLS,
        )
        assert captured[0]["tools"] == SAMPLE_TOOLS

    @pytest.mark.asyncio
    async def test_openai_payload_omits_tools_when_none(self) -> None:
        captured: list[dict[str, Any]] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(json.loads(req.content))
            return httpx.Response(
                200,
                json=_make_tool_call_response(content="hello"),
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        provider = _make_openai_provider(client)
        await provider.chat_with_tools(
            [LLMMessage(role=LLMRole.USER, content="hi")],
            tools=None,
        )
        assert "tools" not in captured[0]


# ---------------------------------------------------------------------------
# Test 2: tool_calls response parsing
# ---------------------------------------------------------------------------


class TestToolCallsParsing:
    @pytest.mark.asyncio
    async def test_parses_tool_calls_correctly(self) -> None:
        tool_calls_data = [
            {
                "id": "call_abc123",
                "type": "function",
                "function": {
                    "name": "market_ticker",
                    "arguments": '{"symbol": "BTC/USDT"}',
                },
            }
        ]
        resp_data = _make_tool_call_response(tool_calls=tool_calls_data)

        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_data)))
        provider = _make_openai_provider(client)
        result = await provider.chat_with_tools(
            [LLMMessage(role=LLMRole.USER, content="btc price")],
            tools=SAMPLE_TOOLS,
        )

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_abc123"
        assert result.tool_calls[0].name == "market_ticker"
        assert result.tool_calls[0].arguments == {"symbol": "BTC/USDT"}

    @pytest.mark.asyncio
    async def test_parses_multiple_tool_calls(self) -> None:
        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "market_ticker", "arguments": '{"symbol": "BTC/USDT"}'},
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "market_ticker", "arguments": '{"symbol": "ETH/USDT"}'},
            },
        ]
        resp_data = _make_tool_call_response(tool_calls=tool_calls_data)
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_data)))
        provider = _make_openai_provider(client)
        result = await provider.chat_with_tools(
            [LLMMessage(role=LLMRole.USER, content="compare")],
            tools=SAMPLE_TOOLS,
        )
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].name == "market_ticker"
        assert result.tool_calls[1].name == "market_ticker"


# ---------------------------------------------------------------------------
# Test 3: usage field parsing
# ---------------------------------------------------------------------------


class TestUsageParsing:
    @pytest.mark.asyncio
    async def test_parses_token_usage(self) -> None:
        usage = {"prompt_tokens": 42, "completion_tokens": 13, "total_tokens": 55}
        resp_data = _make_tool_call_response(content="done", usage=usage, model="gpt-4o-mini")

        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_data)))
        provider = _make_openai_provider(client)
        result = await provider.chat_with_tools(
            [LLMMessage(role=LLMRole.USER, content="hi")],
        )
        assert result.usage.prompt_tokens == 42
        assert result.usage.completion_tokens == 13
        assert result.usage.total_tokens == 55
        assert result.model == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Test 4: text-only response (no tool_calls)
# ---------------------------------------------------------------------------


class TestTextOnlyResponse:
    @pytest.mark.asyncio
    async def test_returns_text_when_no_tool_calls(self) -> None:
        resp_data = _make_tool_call_response(content="BTC is at $67,234")
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_data)))
        provider = _make_openai_provider(client)
        result = await provider.chat_with_tools(
            [LLMMessage(role=LLMRole.USER, content="price?")],
            tools=SAMPLE_TOOLS,
        )
        assert result.tool_calls == []
        assert result.text == "BTC is at $67,234"


# ---------------------------------------------------------------------------
# Test 5: base class fallback (JSON text parsing)
# ---------------------------------------------------------------------------


class TestBaseClassFallback:
    @pytest.mark.asyncio
    async def test_base_class_fallback_returns_text(self) -> None:
        """LLMProvider base fallback should return text-only ToolCallResult."""
        resp_data = {"choices": [{"message": {"role": "assistant", "content": "fallback text"}}]}
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_data)))
        provider = _make_openai_provider(client)

        # Call base class method directly via super (simulate unsupported provider)
        result = await LLMProvider.chat_with_tools(
            provider,
            [LLMMessage(role=LLMRole.USER, content="hi")],
        )
        assert isinstance(result, ToolCallResult)
        assert result.text == "fallback text"
        assert result.tool_calls == []


# ---------------------------------------------------------------------------
# Test 6: error paths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    @pytest.mark.asyncio
    async def test_connection_error_propagates(self) -> None:
        def raise_connect(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.AsyncClient(transport=httpx.MockTransport(raise_connect))
        provider = _make_openai_provider(client)
        with pytest.raises(LLMConnectionError):
            await provider.chat_with_tools(
                [LLMMessage(role=LLMRole.USER, content="hi")],
                tools=SAMPLE_TOOLS,
            )

    @pytest.mark.asyncio
    async def test_invalid_json_response_raises_error(self) -> None:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, text="not json", headers={"content-type": "text/plain"})
            )
        )
        provider = _make_openai_provider(client)
        with pytest.raises(LLMError, match="non-JSON"):
            await provider.chat_with_tools(
                [LLMMessage(role=LLMRole.USER, content="hi")],
                tools=SAMPLE_TOOLS,
            )

    @pytest.mark.asyncio
    async def test_malformed_tool_call_arguments_handled(self) -> None:
        """Invalid JSON in tool_call arguments should be gracefully handled."""
        tool_calls_data = [
            {
                "id": "call_bad",
                "type": "function",
                "function": {
                    "name": "market_ticker",
                    "arguments": "not valid json {{{",
                },
            }
        ]
        resp_data = _make_tool_call_response(tool_calls=tool_calls_data)
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_data)))
        provider = _make_openai_provider(client)
        result = await provider.chat_with_tools(
            [LLMMessage(role=LLMRole.USER, content="hi")],
            tools=SAMPLE_TOOLS,
        )
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].arguments == {}


# ---------------------------------------------------------------------------
# Test 7: Ollama provider tool calling
# ---------------------------------------------------------------------------


class TestOllamaToolCalling:
    @pytest.mark.asyncio
    async def test_ollama_parses_tool_calls(self) -> None:
        ollama_resp = {
            "model": "llama3",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "market_ticker",
                            "arguments": {"symbol": "BTC/USDT"},
                        }
                    }
                ],
            },
            "done": True,
            "prompt_eval_count": 20,
            "eval_count": 8,
        }
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=ollama_resp)))
        provider = _make_ollama_provider(client)
        result = await provider.chat_with_tools(
            [LLMMessage(role=LLMRole.USER, content="btc price")],
            tools=SAMPLE_TOOLS,
        )
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "market_ticker"
        assert result.usage.prompt_tokens == 20
        assert result.usage.completion_tokens == 8

    @pytest.mark.asyncio
    async def test_ollama_fallback_when_no_tools(self) -> None:
        ollama_resp = {
            "model": "llama3",
            "message": {"role": "assistant", "content": "just text"},
            "done": True,
        }
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=ollama_resp)))
        provider = _make_ollama_provider(client)
        result = await provider.chat_with_tools(
            [LLMMessage(role=LLMRole.USER, content="hi")],
            tools=None,
        )
        assert isinstance(result, ToolCallResult)
        assert result.text == "just text"


# ---------------------------------------------------------------------------
# Test 8: Router chat_with_tools fallback chain
# ---------------------------------------------------------------------------


class TestRouterToolCalling:
    @pytest.mark.asyncio
    async def test_router_routes_to_first_provider(self) -> None:
        resp_data = _make_tool_call_response(content="from primary")
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_data)))
        primary = _make_openai_provider(client)
        router = LLMRouter(providers=[("primary", primary)])

        result = await router.chat_with_tools(
            [LLMMessage(role=LLMRole.USER, content="hi")],
            tools=SAMPLE_TOOLS,
        )
        assert result.text == "from primary"

    @pytest.mark.asyncio
    async def test_router_falls_back_on_error(self) -> None:
        error_client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("fail")))
        )
        success_resp = _make_tool_call_response(content="from fallback")
        success_client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=success_resp))
        )

        primary = _make_openai_provider(error_client)
        fallback = _make_openai_provider(success_client)
        router = LLMRouter(providers=[("primary", primary), ("fallback", fallback)])

        result = await router.chat_with_tools(
            [LLMMessage(role=LLMRole.USER, content="hi")],
            tools=SAMPLE_TOOLS,
        )
        assert result.text == "from fallback"
