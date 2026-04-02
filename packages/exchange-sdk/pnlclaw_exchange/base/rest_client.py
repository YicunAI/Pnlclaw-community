"""Base REST client for authenticated exchange API calls.

Provides rate-limited, signed HTTP requests with automatic retries
and standardized error handling. Exchange-specific clients inherit
from this and implement their normalisation logic.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from pnlclaw_exchange.base.auth import BaseAuthenticator
from pnlclaw_exchange.base.rate_limiter import SlidingWindowRateLimiter
from pnlclaw_exchange.exceptions import (
    AuthenticationError,
    ExchangeAPIError,
    RateLimitExceededError,
)

logger = logging.getLogger(__name__)


class BaseRESTClient:
    """Async REST client with authentication, rate limiting, and error handling.

    This is the base class for all exchange-specific REST trading clients.
    Subclasses configure the base URL, authenticator, and override
    ``_handle_error_response`` for exchange-specific error codes.
    """

    def __init__(
        self,
        *,
        base_url: str,
        authenticator: BaseAuthenticator,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        timeout: float = 15.0,
        recv_window: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = authenticator
        self._rate_limiter = rate_limiter or SlidingWindowRateLimiter()
        self._recv_window = recv_window
        self._http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        signed: bool = True,
    ) -> dict[str, Any]:
        """Make an authenticated (or public) REST API request.

        Args:
            method: HTTP method.
            path: API path (e.g. ``/api/v3/order``).
            params: Query parameters.
            body: JSON body for POST/PUT.
            signed: Whether to sign the request.

        Returns:
            Parsed JSON response as dict.

        Raises:
            ExchangeAPIError: On non-2xx responses.
            AuthenticationError: On 401/403.
            RateLimitExceededError: On 429.
        """
        await self._rate_limiter.acquire()

        if params is None:
            params = {}
        if self._recv_window is not None and "recvWindow" not in params:
            params["recvWindow"] = self._recv_window

        headers: dict[str, str] = {}
        body_str: str | None = None
        if body is not None:
            import json

            body_str = json.dumps(body)

        if signed:
            auth_headers = self._auth.sign_request(
                method=method,
                path=path,
                params=params if params else None,
                body=body_str,
            )
            headers.update(auth_headers)

        url = f"{self._base_url}{path}"
        logger.debug("REST %s %s params=%s", method, url, params)

        resp = await self._http.request(
            method=method,
            url=url,
            params=params if method.upper() in ("GET", "DELETE") else None,
            content=body_str if method.upper() in ("POST", "PUT") else None,
            data=params if method.upper() == "POST" and body is None else None,
            headers=headers,
        )

        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            self._rate_limiter.set_retry_after(retry_after)

        if resp.status_code == 429:
            raise RateLimitExceededError(
                f"Rate limit exceeded on {method} {path}",
                exchange=self._exchange_name,
            )

        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed ({resp.status_code}) on {method} {path}",
                exchange=self._exchange_name,
                status_code=resp.status_code,
            )

        if resp.status_code >= 400:
            self._handle_error_response(resp)

        try:
            result: dict[str, Any] = resp.json()
            return result
        except Exception:
            return {"raw": resp.text}

    @property
    def _exchange_name(self) -> str:
        """Override in subclasses to identify the exchange."""
        return "unknown"

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """Parse exchange-specific error codes and raise typed exceptions.

        Override in subclasses for exchange-specific error mapping.
        """
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}

        raise ExchangeAPIError(
            f"API error {resp.status_code}: {data}",
            exchange=self._exchange_name,
            status_code=resp.status_code,
            details=data,
        )
