"""Ollama local LLM provider.

Connects to a local Ollama instance (default ``http://localhost:11434``)
using the ``/api/chat`` endpoint.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

from pnlclaw_llm.base import (
    LLMConfig,
    LLMConnectionError,
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMRole,
)
from pnlclaw_llm.schemas import TokenUsage, ToolCall, ToolCallResult

logger = logging.getLogger(__name__)

_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_TIMEOUT = 120.0  # Local models can be slow on first load


def _messages_to_dicts(messages: list[LLMMessage]) -> list[dict[str, str]]:
    return [{"role": msg.role.value, "content": msg.content} for msg in messages]


class OllamaProvider(LLMProvider):
    """LLM provider for a local Ollama instance.

    Uses Ollama's native ``/api/chat`` endpoint with httpx.
    Does not require an API key.

    Args:
        config: LLM configuration. ``base_url`` defaults to ``http://localhost:11434``.
        timeout: HTTP request timeout in seconds (higher default for local models).
        client: Optional pre-configured httpx.AsyncClient (for testing).
    """

    def __init__(
        self,
        config: LLMConfig,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self._base_url = (config.base_url or _DEFAULT_OLLAMA_URL).rstrip("/")
        self._timeout = timeout
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ----- chat -----

    async def chat(self, messages: list[LLMMessage], **kwargs: Any) -> str:
        """Send messages and return the complete response."""
        payload = self._build_payload(messages, stream=False, **kwargs)
        client = await self._get_client()

        try:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise LLMConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. Is Ollama running? Start it with: ollama serve"
            ) from exc

        if resp.status_code != 200:
            raise LLMError(f"Ollama error ({resp.status_code}): {resp.text}")

        data = cast(dict[str, Any], resp.json())
        message = data.get("message", {})
        if not isinstance(message, dict):
            raise LLMError("Malformed Ollama response: missing message object")
        content = message.get("content", "")
        if not isinstance(content, str):
            raise LLMError("Malformed Ollama response: message content must be string")
        return content

    # ----- chat_stream -----

    async def chat_stream(self, messages: list[LLMMessage], **kwargs: Any) -> AsyncIterator[str]:
        """Stream response text chunks from Ollama (line-delimited JSON)."""
        payload = self._build_payload(messages, stream=True, **kwargs)
        client = await self._get_client()

        try:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise LLMError(f"Ollama error ({resp.status_code}): {body.decode()}")

                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done", False):
                        break
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise LLMConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. Is Ollama running? Start it with: ollama serve"
            ) from exc

    # ----- chat_with_tools -----

    async def chat_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ToolCallResult:
        """Native function calling via Ollama tools API (0.5+).

        Falls back to the base class text-only implementation if the model
        returns no tool calls (indicating no native support).
        """
        if not tools:
            return await super().chat_with_tools(messages, tools=None, **kwargs)

        payload = self._build_payload(messages, stream=False, **kwargs)
        payload["tools"] = tools
        client = await self._get_client()

        try:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise LLMConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. Is Ollama running? Start it with: ollama serve"
            ) from exc

        if resp.status_code != 200:
            logger.warning(
                "Ollama tool calling failed (%s), falling back to text mode",
                resp.status_code,
            )
            return await super().chat_with_tools(messages, tools=None, **kwargs)

        data = cast(dict[str, Any], resp.json())
        message = data.get("message", {})
        if not isinstance(message, dict):
            return await super().chat_with_tools(messages, tools=None, **kwargs)

        text_content = message.get("content", "") or None
        raw_tool_calls = message.get("tool_calls", [])
        parsed_calls: list[ToolCall] = []

        if isinstance(raw_tool_calls, list):
            for i, tc in enumerate(raw_tool_calls):
                if not isinstance(tc, dict):
                    continue
                func = tc.get("function", {})
                if not isinstance(func, dict):
                    continue
                parsed_calls.append(
                    ToolCall(
                        id=f"ollama_call_{i}",
                        name=func.get("name", ""),
                        arguments=func.get("arguments", {}),
                    )
                )

        usage_data = data.get("prompt_eval_count", 0), data.get("eval_count", 0)
        token_usage = TokenUsage(
            prompt_tokens=usage_data[0],
            completion_tokens=usage_data[1],
            total_tokens=usage_data[0] + usage_data[1],
        )

        return ToolCallResult(
            tool_calls=parsed_calls,
            text=text_content if text_content else None,
            model=data.get("model", self._config.model),
            usage=token_usage,
        )

    # ----- generate_structured -----

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        output_schema: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a JSON response using Ollama's ``format`` parameter."""
        schema_instruction = (
            "You must respond with valid JSON only, no markdown, no explanation. "
            f"Your response must conform to this JSON schema:\n{json.dumps(output_schema)}"
        )
        augmented = [LLMMessage(role=LLMRole.SYSTEM, content=schema_instruction)] + list(messages)
        payload = self._build_payload(augmented, stream=False, **kwargs)
        payload["format"] = "json"

        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise LLMConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. Is Ollama running? Start it with: ollama serve"
            ) from exc

        if resp.status_code != 200:
            raise LLMError(f"Ollama error ({resp.status_code}): {resp.text}")

        data = cast(dict[str, Any], resp.json())
        message = data.get("message", {})
        if not isinstance(message, dict):
            raise LLMError("Malformed Ollama response: missing message object")
        raw_text = message.get("content", "")
        if not isinstance(raw_text, str):
            raise LLMError("Malformed Ollama response: message content must be string")
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Failed to parse Ollama JSON output: {raw_text[:200]}") from exc
        if not isinstance(parsed, dict):
            raise LLMError("Structured output must be a JSON object")
        return cast(dict[str, Any], parsed)

    # ----- helpers -----

    def _build_payload(
        self,
        messages: list[LLMMessage],
        *,
        stream: bool,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": kwargs.get("model", self._config.model),
            "messages": _messages_to_dicts(messages),
            "stream": stream,
            "options": {
                "temperature": kwargs.get("temperature", self._config.temperature),
                "num_predict": kwargs.get("max_tokens", self._config.max_tokens),
            },
        }
        return payload
