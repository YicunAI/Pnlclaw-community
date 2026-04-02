"""OpenAI-compatible LLM provider using httpx (no openai SDK dependency).

Supports OpenAI, DeepSeek, OpenRouter, and any provider exposing
the ``/v1/chat/completions`` endpoint via ``base_url`` configuration.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

from pnlclaw_core.resilience.backoff import BackoffPolicy
from pnlclaw_core.resilience.retry import retry_async
from pnlclaw_llm.base import (
    LLMAuthError,
    LLMConfig,
    LLMConnectionError,
    LLMContextLengthError,
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMRateLimitError,
    LLMRole,
)
from pnlclaw_llm.schemas import TokenUsage, ToolCall, ToolCallResult

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_TIMEOUT = 60.0
_RETRY_MAX_ATTEMPTS = 3


def _build_headers(api_key: str | None) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _messages_to_dicts(messages: list[LLMMessage | dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert messages to OpenAI API dicts, preserving tool-calling fields.

    For multi-turn function calling the API requires:
    - assistant messages with ``tool_calls`` array and possibly ``content: null``
    - tool messages with ``tool_call_id`` linking back to the call
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")

            if role == "assistant" and "tool_calls" in msg:
                entry: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.get("content"),
                    "tool_calls": msg["tool_calls"],
                }
                result.append(entry)
            elif role == "tool":
                entry = {
                    "role": "tool",
                    "content": msg.get("content", ""),
                }
                if "tool_call_id" in msg:
                    entry["tool_call_id"] = msg["tool_call_id"]
                result.append(entry)
            else:
                result.append({"role": role, "content": msg.get("content", "")})
        else:
            result.append({"role": msg.role.value, "content": msg.content})
    return result


_CTX_LENGTH_PATTERNS = (
    "context_length_exceeded",
    "maximum context length",
    "max_tokens",
    "too many tokens",
    "context window",
    "reduce the length",
    "input too long",
    "request too large",
)


def _classify_http_error(status_code: int, body: str) -> LLMError:
    """Map HTTP status codes to typed LLM exceptions."""
    if status_code == 401 or status_code == 403:
        return LLMAuthError(f"Authentication failed ({status_code}): {body}")
    if status_code == 429:
        return LLMRateLimitError(f"Rate limit exceeded: {body}")
    if status_code >= 500:
        return LLMConnectionError(f"Server error ({status_code}): {body}")
    body_lower = body.lower()
    if status_code == 400 and any(p in body_lower for p in _CTX_LENGTH_PATTERNS):
        return LLMContextLengthError(f"Context length exceeded: {body[:300]}")
    return LLMError(f"API error ({status_code}): {body}")


_MARKDOWN_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) that some models wrap around JSON."""
    stripped = text.strip()
    m = _MARKDOWN_FENCE_RE.match(stripped)
    return m.group(1).strip() if m else stripped


def _strip_think_tags(text: str) -> str:
    """Remove ``<think>...</think>`` blocks from content.

    DeepSeek R1 open-source and some proxies embed reasoning
    inside ``<think>`` tags in the ``content`` field.
    """
    return _THINK_TAG_RE.sub("", text).strip()


def _should_retry_llm(exc: Exception) -> bool:
    """Retry on connection and rate-limit errors, not on auth errors."""
    if isinstance(exc, LLMAuthError):
        return False
    if isinstance(exc, (LLMConnectionError, LLMRateLimitError)):
        return True
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
        return True
    return False


def _normalize_base_url(url: str) -> str:
    """Ensure base URL points to an OpenAI-compatible API root.

    Handles common user inputs::

        https://api.openai.com/v1                → kept as-is
        https://api.deepseek.com                 → /v1 appended
        https://proxy.example.com                → /v1 appended
        https://proxy.example.com/v1/            → trailing slash stripped
        https://proxy.example.com/v1/chat/completions → trimmed to /v1
        https://generativelanguage.googleapis.com/v1beta → kept as-is
    """
    url = url.strip().rstrip("/")

    # User accidentally pasted a full endpoint path — trim back to API root
    for suffix in ("/chat/completions", "/completions", "/models", "/embeddings"):
        if url.endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")
            break

    if url.endswith("/v1") or "/v1/" in url:
        return url
    if "/v1beta" in url:
        return url
    return f"{url}/v1"


def _wrap_tool_definitions(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert flat tool definitions to OpenAI function-calling format.

    Input:  [{"name": "x", "description": "...", "parameters": {...}}]
    Output: [{"type": "function", "function": {"name": "x", ...}}]

    Already-wrapped definitions (with "type": "function") are passed through.
    """
    wrapped: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") == "function" and "function" in tool:
            wrapped.append(tool)
        else:
            wrapped.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                    },
                }
            )
    return wrapped


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
        raw_url = config.base_url or _DEFAULT_BASE_URL
        self._base_url = _normalize_base_url(raw_url)
        if self._base_url != raw_url.rstrip("/"):
            logger.info("Normalized base_url: %s → %s", raw_url, self._base_url)
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

    # ----- list_models -----

    async def list_models(self) -> list[dict[str, Any]]:
        """Fetch available models from the provider's /models endpoint.

        Returns:
            List of model dicts with 'id' and optional metadata.

        Raises:
            LLMError: On any API failure.
        """
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self._base_url}/models",
                headers=_build_headers(self._config.api_key),
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise LLMConnectionError(str(exc)) from exc

        if resp.status_code != 200:
            raise _classify_http_error(resp.status_code, resp.text)

        try:
            raw_data = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            content_type = resp.headers.get("content-type", "")
            if "html" in content_type.lower():
                raise LLMError(
                    f"Provider returned HTML instead of JSON. Check your base_url configuration. "
                    f"Expected: {self._base_url}/models"
                ) from exc
            raise LLMError(f"Failed to parse models response as JSON: {resp.text[:200]}") from exc

        data = cast(dict[str, Any], raw_data)
        models_raw = data.get("data", [])
        if not isinstance(models_raw, list):
            raise LLMError("Invalid models response format")
        return cast(list[dict[str, Any]], models_raw)

    # ----- chat -----

    async def chat(self, messages: list[LLMMessage | dict[str, Any]], **kwargs: Any) -> str:
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

            try:
                raw_data = resp.json()
            except (json.JSONDecodeError, ValueError) as exc:
                content_type = resp.headers.get("content-type", "")
                if "html" in content_type.lower() or resp.text.strip().startswith("<!"):
                    raise LLMError(
                        f"Provider returned HTML instead of JSON — "
                        f"check base_url (current: {self._base_url}). "
                        f"It may need '/v1' appended."
                    ) from exc
                raise LLMError(f"Provider returned non-JSON response: {resp.text[:200]}") from exc

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

    async def chat_stream(self, messages: list[LLMMessage | dict[str, Any]], **kwargs: Any) -> AsyncIterator[str]:
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

                in_think_block = False

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
                    choices = chunk.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    if not isinstance(delta, dict):
                        continue

                    # Skip Claude extended thinking deltas
                    delta_type = delta.get("type", "")
                    if delta_type in ("thinking", "redacted_thinking"):
                        continue

                    # Skip DeepSeek reasoning_content tokens
                    if "reasoning_content" in delta and "content" not in delta:
                        continue

                    content = delta.get("content")
                    if not content:
                        continue

                    if isinstance(content, list):
                        text = _extract_text_from_blocks(content)
                        if text:
                            yield text
                        continue

                    text = str(content)
                    # Handle <think> tags in streaming (DeepSeek R1 open-source)
                    if "<think>" in text:
                        in_think_block = True
                        text = text.split("<think>")[0]
                        if text:
                            yield text
                        continue
                    if "</think>" in text:
                        in_think_block = False
                        text = text.split("</think>", 1)[-1]
                        if text:
                            yield text
                        continue
                    if in_think_block:
                        continue

                    yield text
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise LLMConnectionError(str(exc)) from exc

    # ----- generate_structured -----

    async def generate_structured(
        self,
        messages: list[LLMMessage | dict[str, Any]],
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
            raw_text = _strip_markdown_fences(self._extract_content(data))
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                raise LLMError(f"Failed to parse structured output as JSON: {raw_text[:200]}") from exc
            if not isinstance(parsed, dict):
                raise LLMError("Structured output must be a JSON object")
            return cast(dict[str, Any], parsed)

        async def _fallback_without_format(client: httpx.AsyncClient) -> dict[str, Any]:
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
                try:
                    return await _parse_response(resp)
                except LLMError:
                    logger.debug("JSON parse failed with response_format, falling back")
                    return await _fallback_without_format(client)

            if resp.status_code in (400, 422, 500):
                return await _fallback_without_format(client)

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

    # ----- chat_with_tools -----

    async def chat_with_tools(
        self,
        messages: list[LLMMessage | dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ToolCallResult:
        """Native function calling via OpenAI-compatible tools API.

        Sends ``tools`` in the request payload and parses ``tool_calls``
        from the response. Falls back to text-only if no tool calls are
        returned.
        """
        payload = self._build_payload(messages, stream=False, tools=tools, **kwargs)

        async def _do_request() -> ToolCallResult:
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

            try:
                raw_data = resp.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise LLMError(f"Provider returned non-JSON response: {resp.text[:200]}") from exc

            data = cast(dict[str, Any], raw_data)
            return self._parse_tool_call_response(data)

        return cast(
            ToolCallResult,
            await retry_async(
                _do_request,
                max_attempts=_RETRY_MAX_ATTEMPTS,
                policy=BackoffPolicy(initial=1.0, max_delay=10.0),
                should_retry=_should_retry_llm,
            ),
        )

    @staticmethod
    def _parse_tool_call_response(data: dict[str, Any]) -> ToolCallResult:
        """Parse an OpenAI-compatible response into a ToolCallResult."""
        usage_data = data.get("usage", {})
        token_usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        model_name = data.get("model", "")

        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return ToolCallResult(model=model_name, usage=token_usage)

        message = choices[0].get("message", {})
        if not isinstance(message, dict):
            return ToolCallResult(model=model_name, usage=token_usage)

        text_content = message.get("content")
        if isinstance(text_content, str):
            text_content = _strip_think_tags(text_content) or None
        else:
            text_content = None

        raw_tool_calls = message.get("tool_calls", [])
        parsed_calls: list[ToolCall] = []
        if isinstance(raw_tool_calls, list):
            for tc in raw_tool_calls:
                if not isinstance(tc, dict):
                    continue
                tc_id = tc.get("id", "")
                func = tc.get("function", {})
                if not isinstance(func, dict):
                    continue
                name = func.get("name", "")
                args_raw = func.get("arguments", "{}")
                try:
                    arguments = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    if not isinstance(arguments, dict):
                        arguments = {}
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "tool_call_args_parse_failed",
                        extra={"tool": name, "raw_args": str(args_raw)[:200]},
                    )
                    arguments = {}
                parsed_calls.append(ToolCall(id=tc_id, name=name, arguments=arguments))

        return ToolCallResult(
            tool_calls=parsed_calls,
            text=text_content,
            model=model_name,
            usage=token_usage,
        )

    # ----- helpers -----

    def _build_payload(
        self,
        messages: list[LLMMessage | dict[str, Any]],
        *,
        stream: bool,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": kwargs.get("model", self._config.model),
            "messages": _messages_to_dicts(messages),
            "temperature": kwargs.get("temperature", self._config.temperature),
            "max_tokens": kwargs.get("max_tokens", self._config.max_tokens),
            "stream": stream,
        }
        if tools:
            payload["tools"] = _wrap_tool_definitions(tools)
            payload["tool_choice"] = "auto"
        return payload

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        """Extract assistant text from a chat completions response.

        Handles provider quirks:
        - ``content: null`` (Claude proxies, tool-call-only turns)
        - ``choices: []`` (some providers on empty response)
        - Content block arrays with thinking/text blocks (Claude)
        - Nested ``output``/``text`` keys (non-standard providers)
        """
        # Some non-standard APIs put content at top level
        if "output" in data and isinstance(data["output"], str):
            return data["output"]

        choices_raw = data.get("choices")
        if not isinstance(choices_raw, list) or not choices_raw:
            for key in ("result", "response", "content"):
                val = data.get(key)
                if isinstance(val, str):
                    return val
            raise LLMError(f"Empty choices in API response: {list(data.keys())}")

        first_choice = choices_raw[0]
        if not isinstance(first_choice, dict):
            raise LLMError("Malformed choices in API response")

        message = first_choice.get("message", {})
        if not isinstance(message, dict):
            raise LLMError("Malformed message in API response")

        content = message.get("content")
        if content is None:
            return ""
        if isinstance(content, str):
            return _strip_think_tags(content)
        if isinstance(content, list):
            return _extract_text_from_blocks(content)
        return _strip_think_tags(str(content))


def _extract_text_from_blocks(blocks: list[Any]) -> str:
    """Extract visible text from a content block array.

    Claude and some proxies return content as an array of typed blocks::

        [
            {"type": "thinking", "thinking": "internal reasoning..."},
            {"type": "text", "text": "Hello! How can I help?"}
        ]

    We skip ``thinking`` blocks and concatenate ``text`` blocks.
    """
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            parts.append(str(block))
            continue

        block_type = block.get("type", "")

        # Skip thinking / redacted_thinking blocks
        if block_type in ("thinking", "redacted_thinking"):
            continue

        # Standard text block
        if block_type == "text":
            text = block.get("text", "")
            if text:
                parts.append(text)
            continue

        # tool_use blocks — skip (handled elsewhere)
        if block_type == "tool_use":
            continue

        # Fallback: try common keys
        for key in ("text", "content", "value"):
            val = block.get(key)
            if isinstance(val, str) and val:
                parts.append(val)
                break
        else:
            # Unknown block type with no text key — stringify if non-empty
            if block_type and block_type not in ("thinking", "tool_use"):
                parts.append(str(block))

    return "".join(parts)
