"""Tests for the OKX REST trading client."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from pnlclaw_exchange.base.auth import ExchangeCredentials
from pnlclaw_exchange.exchanges.okx.rest_client import (
    OKXOrderType,
    OKXRESTClient,
    OKXTradeMode,
)
from pnlclaw_exchange.exceptions import (
    AuthenticationError,
    ExchangeAPIError,
    InsufficientBalanceError,
    InvalidOrderError,
    OrderNotFoundError,
    OrderRejectedError,
)


def _make_creds() -> ExchangeCredentials:
    return ExchangeCredentials(
        api_key=SecretStr("okx-key"),
        api_secret=SecretStr("okx-secret"),
        passphrase=SecretStr("okx-pass"),
    )


def _make_client(**kwargs: Any) -> OKXRESTClient:
    return OKXRESTClient(_make_creds(), demo=True, **kwargs)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestOKXOrderValidation:
    def test_limit_order_requires_price(self) -> None:
        with pytest.raises(InvalidOrderError, match="price"):
            OKXRESTClient._validate_order_params({
                "instId": "BTC-USDT",
                "tdMode": "cash",
                "side": "buy",
                "ordType": "limit",
                "sz": "0.01",
            })

    def test_market_order_no_price_needed(self) -> None:
        OKXRESTClient._validate_order_params({
            "instId": "BTC-USDT",
            "tdMode": "cash",
            "side": "buy",
            "ordType": "market",
            "sz": "0.01",
        })

    def test_post_only_requires_price(self) -> None:
        with pytest.raises(InvalidOrderError, match="price"):
            OKXRESTClient._validate_order_params({
                "instId": "BTC-USDT",
                "tdMode": "cash",
                "side": "buy",
                "ordType": "post_only",
                "sz": "0.01",
            })


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestOKXErrorHandling:
    def test_auth_error(self) -> None:
        client = _make_client()
        with pytest.raises(AuthenticationError):
            client._handle_okx_error({"code": "50101", "msg": "Invalid key", "data": []})

    def test_insufficient_balance(self) -> None:
        client = _make_client()
        with pytest.raises(InsufficientBalanceError):
            client._handle_okx_error({
                "code": "1", "msg": "",
                "data": [{"sCode": "51008", "sMsg": "Insufficient balance"}],
            })

    def test_order_not_found(self) -> None:
        client = _make_client()
        with pytest.raises(OrderNotFoundError):
            client._handle_okx_error({
                "code": "1", "msg": "",
                "data": [{"sCode": "51603", "sMsg": "Order does not exist"}],
            })

    def test_order_rejected(self) -> None:
        client = _make_client()
        with pytest.raises(OrderRejectedError):
            client._handle_okx_error({
                "code": "1", "msg": "",
                "data": [{"sCode": "51000", "sMsg": "Parameter error"}],
            })

    def test_generic_error(self) -> None:
        client = _make_client()
        with pytest.raises(ExchangeAPIError):
            client._handle_okx_error({
                "code": "99999", "msg": "Unknown error", "data": [],
            })

    def test_cancel_requires_id(self) -> None:
        client = _make_client()
        with pytest.raises(InvalidOrderError, match="order_id or client_order_id"):
            import asyncio
            asyncio.run(client.cancel_order(inst_id="BTC-USDT"))


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


class TestOKXClientConstruction:
    def test_default_url(self) -> None:
        client = OKXRESTClient(_make_creds())
        assert "okx.com" in client._base_url

    def test_exchange_name(self) -> None:
        client = _make_client()
        assert client._exchange_name == "okx"

    def test_demo_mode(self) -> None:
        client = OKXRESTClient(_make_creds(), demo=True)
        assert client._demo is True
