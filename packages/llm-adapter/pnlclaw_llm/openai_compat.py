"""OpenAI-compatible LLM provider using httpx (no openai SDK dependency).

Supports OpenAI, DeepSeek, OpenRouter, and any provider exposing
the ``/v1/chat/completions`` endpoint via ``base_url`` configuration.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

from pnlclaw_core.resilience.backoff import BackoffPolicy
from pnlclaw_core.resilience.retry import retry_async
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

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_TIMEOUT = 60.0
_RETRY_MAX_ATTEMPTS = 3


def _build_headers(api_key: str | None) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _messages_to_dicts(messages: list[LLMMessage]) -> list[dict[str, str]]:
    return [{"role": msg.role.value, "content": msg.content} for msg in messages]


def _classify_http_error(status_code: int, body: str) -> LLMError:
    """Map HTTP status codes to typed LLM exceptions."""
    if status_code == 401 or status_code == 403:
        return LLMAuthError(f"Authentication failed ({status_code}): {body}")
    if status_code == 429:
        return LLMRateLimitError(f"Rate limit exceeded: {body}")
    if status_code >= 500:
        return LLMConnectionError(f"Server error ({status_code}): {body}")
    return LLMError(f"API error ({status_code}): {body}")


def _should_retry_llm(exc: Exception) -> bool:
    """Retry on connection and rate-limit errors, not on auth errors."""
    if isinstance(exc, LLMAuthError):
        return False
    if isinstance(exc, (LLMConnectionError, LLMRateLimitError)):
        return True
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
        return True
    return False


class OpenAICompatProvider(LLMProvider):
    """LLM provider for OpenAI-compatible APIs.

    Uses httpx for async HTTP. Supports any service exposing the
    ``/v1/chat/completions`` endpoint (OpenAI, DeepSeek, OpenRouter, etc.).

    Args:
        config: LLM configuration (model, api_key, base_url, etc.).
        timeout: HTTP request timeout in seconds.
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
        self._base_url = (config.base_url or _DEFAULT_BASE_URL).rstrip("/")
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
        """Send messages and return the complete response text."""
        payload = self._build_payload(messages, stream=False, **kwargs)

        async def _do_request() -> str:
            client = await self._get_client()
            try:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=_build_headers(self._config.api_key),
                    json=payload,
                )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                raise LLMConnectionError(str(exc)) from exc

            if resp.status_code != 200:
                raise _classify_http_error(resp.status_code, resp.text)

            raw_data = resp.json()
            data = cast(dict[str, Any], raw_data)
            return self._extract_content(data)

        return cast(
            str,
            await retry_async(
                _do_request,
                max_attempts=_RETRY_MAX_ATTEMPTS,
                policy=BackoffPolicy(initial=1.0, max_delay=10.0),
                should_retry=_should_retry_llm,
            ),
        )

    # ----- chat_stream -----

    async def chat_stream(self, messages: list[LLMMessage], **kwargs: Any) -> AsyncIterator[str]:
        """Stream response text chunks via SSE."""
        payload = self._build_payload(messages, stream=True, **kwargs)
        client = await self._get_client()

        try:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=_build_headers(self._config.api_key),
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise _classify_http_error(resp.status_code, body.decode())

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[len("data: ") :]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise LLMConnectionError(str(exc)) from exc

    # ----- generate_structured -----

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        output_schema: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a JSON response constrained by *output_schema*.

        Attempts ``response_format=json_object`` first. Falls back to
        instructing the model via system prompt if the provider doesn't
        support structured output natively.
        """
        # Inject JSON instruction into messages
        schema_instruction = (
            "You must respond with valid JSON only, no markdown, no explanation. "
            f"Your response must conform to this JSON schema:\n{json.dumps(output_schema)}"
        )
        augmented = [LLMMessage(role=LLMRole.SYSTEM, content=schema_instruction)] + list(messages)

        payload_with_response_format = self._build_payload(augmented, stream=False, **kwargs)
        payload_with_response_format["response_format"] = {"type": "json_object"}
        payload_without_response_format = self._build_payload(augmented, stream=False, **kwargs)

        async def _parse_response(resp: httpx.Response) -> dict[str, Any]:
            raw_data = resp.json()
            data = cast(dict[str, Any], raw_data)
            raw_text = self._extract_content(data)
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                raise LLMError(
                    f"Failed to parse structured output as JSON: {raw_text[:200]}"
                ) from exc
            if not isinstance(parsed, dict):
                raise LLMError("Structured output must be a JSON object")
            return cast(dict[str, Any], parsed)

        async def _do_request() -> dict[str, Any]:
            client = await self._get_client()
            try:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=_build_headers(self._config.api_key),
                    json=payload_with_response_format,
                )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                raise LLMConnectionError(str(exc)) from exc

            if resp.status_code == 200:
                return await _parse_response(resp)

            if resp.status_code in (400, 422):
                try:
                    fallback_resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=_build_headers(self._config.api_key),
                        json=payload_without_response_format,
                    )
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    raise LLMConnectionError(str(exc)) from exc

                if fallback_resp.status_code == 200:
                    return await _parse_response(fallback_resp)
                raise _classify_http_error(fallback_resp.status_code, fallback_resp.text)

            raise _classify_http_error(resp.status_code, resp.text)

        return cast(
            dict[str, Any],
            await retry_async(
                _do_request,
                max_attempts=_RETRY_MAX_ATTEMPTS,
                policy=BackoffPolicy(initial=1.0, max_delay=10.0),
                should_retry=_should_retry_llm,
            ),
        )

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
            "temperature": kwargs.get("temperature", self._config.temperature),
            "max_tokens": kwargs.get("max_tokens", self._config.max_tokens),
            "stream": stream,
        }
        return payload

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices_raw = data.get("choices", [])
        if not isinstance(choices_raw, list) or not choices_raw:
            raise LLMError("Empty choices in API response")

        first_choice = choices_raw[0]
        if not isinstance(first_choice, dict):
            raise LLMError("Malformed choices in API response")

        message = first_choice.get("message", {})
        if not isinstance(message, dict):
            raise LLMError("Malformed message in API response")

        content = message.get("content", "")
        if not isinstance(content, str):
            raise LLMError("Malformed message content in API response")
        return content
