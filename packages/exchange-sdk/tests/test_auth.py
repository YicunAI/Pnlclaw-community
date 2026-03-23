"""Tests for exchange authentication modules."""

from __future__ import annotations

import hashlib
import hmac
import base64
import time
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from pnlclaw_exchange.base.auth import (
    BinanceAuthenticator,
    ExchangeCredentials,
    OKXAuthenticator,
)


# ---------------------------------------------------------------------------
# ExchangeCredentials
# ---------------------------------------------------------------------------


class TestExchangeCredentials:
    def test_secrets_are_hidden(self) -> None:
        creds = ExchangeCredentials(
            api_key=SecretStr("my-key"), api_secret=SecretStr("my-secret")
        )
        assert "my-key" not in str(creds)
        assert "my-secret" not in str(creds)
        assert creds.api_key.get_secret_value() == "my-key"

    def test_passphrase_optional(self) -> None:
        creds = ExchangeCredentials(
            api_key=SecretStr("k"), api_secret=SecretStr("s")
        )
        assert creds.passphrase is None


# ---------------------------------------------------------------------------
# BinanceAuthenticator
# ---------------------------------------------------------------------------


class TestBinanceAuth:
    def _make_auth(self) -> BinanceAuthenticator:
        creds = ExchangeCredentials(
            api_key=SecretStr("test-api-key"),
            api_secret=SecretStr("test-secret"),
        )
        return BinanceAuthenticator(creds)

    def test_sign_request_returns_api_key_header(self) -> None:
        auth = self._make_auth()
        headers = auth.sign_request(
            "POST", "/api/v3/order",
            params={"symbol": "BTCUSDT", "side": "BUY"},
            timestamp=1000000,
        )
        assert headers["X-MBX-APIKEY"] == "test-api-key"

    def test_sign_request_adds_signature_to_params(self) -> None:
        auth = self._make_auth()
        params = {"symbol": "BTCUSDT", "side": "BUY"}
        auth.sign_request("POST", "/api/v3/order", params=params, timestamp=1000)
        assert "signature" in params
        assert "timestamp" in params
        assert params["timestamp"] == "1000"

    def test_signature_is_hmac_sha256(self) -> None:
        auth = self._make_auth()
        params = {"symbol": "BTCUSDT", "side": "BUY"}
        auth.sign_request("POST", "/api/v3/order", params=params, timestamp=12345)

        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "signature")
        expected = hmac.new(
            b"test-secret",
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert params["signature"] == expected

    def test_auto_timestamp_when_none(self) -> None:
        auth = self._make_auth()
        params: dict = {}
        auth.sign_request("GET", "/test", params=params)
        assert "timestamp" in params
        assert int(params["timestamp"]) > 0


# ---------------------------------------------------------------------------
# OKXAuthenticator
# ---------------------------------------------------------------------------


class TestOKXAuth:
    def _make_auth(self) -> OKXAuthenticator:
        creds = ExchangeCredentials(
            api_key=SecretStr("okx-key"),
            api_secret=SecretStr("okx-secret"),
            passphrase=SecretStr("okx-pass"),
        )
        return OKXAuthenticator(creds)

    def test_sign_request_returns_all_headers(self) -> None:
        auth = self._make_auth()
        headers = auth.sign_request(
            "POST", "/api/v5/trade/order", body='{"instId":"BTC-USDT"}',
            timestamp="2020-12-08T09:08:57.000Z",
        )
        assert headers["OK-ACCESS-KEY"] == "okx-key"
        assert headers["OK-ACCESS-PASSPHRASE"] == "okx-pass"
        assert headers["OK-ACCESS-TIMESTAMP"] == "2020-12-08T09:08:57.000Z"
        assert "OK-ACCESS-SIGN" in headers

    def test_signature_is_base64_hmac(self) -> None:
        auth = self._make_auth()
        ts = "2020-12-08T09:08:57.000Z"
        path = "/api/v5/trade/order"
        body = '{"instId":"BTC-USDT"}'

        headers = auth.sign_request("POST", path, body=body, timestamp=ts)

        prehash = ts + "POST" + path + body
        expected = base64.b64encode(
            hmac.new(b"okx-secret", prehash.encode("utf-8"), hashlib.sha256).digest()
        ).decode("utf-8")
        assert headers["OK-ACCESS-SIGN"] == expected

    def test_get_with_params_includes_query_in_signature(self) -> None:
        auth = self._make_auth()
        params = {"ccy": "BTC"}
        headers = auth.sign_request(
            "GET", "/api/v5/account/balance", params=params,
            timestamp="2020-12-08T09:08:57.000Z",
        )
        assert "OK-ACCESS-SIGN" in headers

    def test_missing_passphrase_raises(self) -> None:
        creds = ExchangeCredentials(
            api_key=SecretStr("k"), api_secret=SecretStr("s")
        )
        auth = OKXAuthenticator(creds)
        with pytest.raises(ValueError, match="passphrase"):
            auth.sign_request("GET", "/test")
