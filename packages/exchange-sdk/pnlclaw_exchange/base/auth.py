"""Authentication base classes for exchange REST APIs.

Provides a Protocol and concrete implementations for:
- HMAC-SHA256 (Binance)
- HMAC-SHA256 + Base64 (OKX)
- API-key-based CLOB authentication (Polymarket)
"""

from __future__ import annotations

import hashlib
import hmac
import base64
import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field, SecretStr


class ExchangeCredentials(BaseModel):
    """Credentials for authenticating with an exchange REST API.

    Secrets are stored as SecretStr to prevent accidental logging.
    """

    api_key: SecretStr = Field(..., description="API key / access key")
    api_secret: SecretStr = Field(..., description="API secret / secret key")
    passphrase: SecretStr | None = Field(
        None, description="Additional passphrase (required by OKX)"
    )

    model_config = {"json_schema_extra": {"examples": [{"api_key": "***", "api_secret": "***"}]}}


class BaseAuthenticator(ABC):
    """Abstract authenticator that signs REST API requests.

    Each exchange subclass implements its specific signing algorithm.
    """

    def __init__(self, credentials: ExchangeCredentials) -> None:
        self._credentials = credentials

    @property
    def api_key(self) -> str:
        return self._credentials.api_key.get_secret_value()

    @property
    def api_secret(self) -> str:
        return self._credentials.api_secret.get_secret_value()

    @abstractmethod
    def sign_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: str | None = None,
        timestamp: int | str | None = None,
    ) -> dict[str, str]:
        """Return headers (and/or query modifications) needed for authentication.

        Args:
            method: HTTP method (GET, POST, DELETE).
            path: Request path (e.g. ``/api/v3/order``).
            params: Query parameters as a dict.
            body: JSON body string (for POST requests).
            timestamp: Request timestamp. If None, generated automatically.

        Returns:
            Dict of HTTP headers to attach to the request.
        """


class BinanceAuthenticator(BaseAuthenticator):
    """HMAC-SHA256 authenticator for Binance Spot REST API.

    Signing algorithm:
        1. Concatenate all query params as ``key=value&key=value``
        2. HMAC-SHA256 with the secret key
        3. Append ``signature`` param to the request
        4. Send API key via ``X-MBX-APIKEY`` header
    """

    def sign_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: str | None = None,
        timestamp: int | str | None = None,
    ) -> dict[str, str]:
        if timestamp is None:
            timestamp = int(time.time() * 1000)

        if params is None:
            params = {}
        params["timestamp"] = str(timestamp)

        query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        params["signature"] = signature

        return {"X-MBX-APIKEY": self.api_key}


class OKXAuthenticator(BaseAuthenticator):
    """HMAC-SHA256 + Base64 authenticator for OKX REST API v5.

    Signing algorithm:
        1. Prehash string = ``timestamp + method + requestPath + body``
        2. HMAC-SHA256 with the secret key
        3. Base64 encode the result
        4. Send via ``OK-ACCESS-SIGN`` header

    Required headers:
        OK-ACCESS-KEY, OK-ACCESS-SIGN, OK-ACCESS-TIMESTAMP, OK-ACCESS-PASSPHRASE
    """

    @property
    def passphrase(self) -> str:
        if self._credentials.passphrase is None:
            raise ValueError("OKX requires a passphrase in credentials")
        return self._credentials.passphrase.get_secret_value()

    def sign_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: str | None = None,
        timestamp: int | str | None = None,
    ) -> dict[str, str]:
        if timestamp is None:
            ts_str = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        else:
            ts_str = str(timestamp)

        request_path = path
        if params:
            query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            request_path = f"{path}?{query}"

        prehash = ts_str + method.upper() + request_path + (body or "")
        mac = hmac.new(
            self.api_secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        )
        signature = base64.b64encode(mac.digest()).decode("utf-8")

        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": ts_str,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }
