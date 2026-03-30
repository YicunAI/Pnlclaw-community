"""Tests for the Binance REST trading client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from pnlclaw_exchange.base.auth import ExchangeCredentials
from pnlclaw_exchange.exchanges.binance.rest_client import (
    BinanceOrderType,
    BinanceRESTClient,
    BinanceTimeInForce,
)
from pnlclaw_exchange.exceptions import (
    AuthenticationError,
    InsufficientBalanceError,
    InvalidOrderError,
    OrderNotFoundError,
    OrderRejectedError,
    RateLimitExceededError,
)


def _make_creds() -> ExchangeCredentials:
    return ExchangeCredentials(
        api_key=SecretStr("test-key"),
        api_secret=SecretStr("test-secret"),
    )


def _make_client(**kwargs: Any) -> BinanceRESTClient:
    return BinanceRESTClient(_make_creds(), testnet=True, **kwargs)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestBinanceOrderValidation:
    def test_limit_order_requires_price(self) -> None:
        with pytest.raises(InvalidOrderError, match="price"):
            BinanceRESTClient._validate_order_params({
                "type": "LIMIT", "quantity": "1", "timeInForce": "GTC",
            })

    def test_limit_order_requires_time_in_force(self) -> None:
        with pytest.raises(InvalidOrderError, match="timeInForce"):
            BinanceRESTClient._validate_order_params({
                "type": "LIMIT", "quantity": "1", "price": "100",
            })

    def test_limit_order_requires_quantity(self) -> None:
        with pytest.raises(InvalidOrderError, match="quantity"):
            BinanceRESTClient._validate_order_params({
                "type": "LIMIT", "price": "100", "timeInForce": "GTC",
            })

    def test_market_order_requires_quantity_or_quote(self) -> None:
        with pytest.raises(InvalidOrderError, match="quantity"):
            BinanceRESTClient._validate_order_params({"type": "MARKET"})

    def test_market_order_accepts_quote_qty(self) -> None:
        BinanceRESTClient._validate_order_params({
            "type": "MARKET", "quoteOrderQty": "100",
        })

    def test_stop_loss_requires_stop_price(self) -> None:
        with pytest.raises(InvalidOrderError, match="stopPrice"):
            BinanceRESTClient._validate_order_params({
                "type": "STOP_LOSS", "quantity": "1",
            })

    def test_stop_loss_limit_requires_all_fields(self) -> None:
        with pytest.raises(InvalidOrderError):
            BinanceRESTClient._validate_order_params({
                "type": "STOP_LOSS_LIMIT",
                "quantity": "1", "price": "100",
            })

    def test_valid_limit_order(self) -> None:
        BinanceRESTClient._validate_order_params({
            "type": "LIMIT", "quantity": "1", "price": "100", "timeInForce": "GTC",
        })


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestBinanceErrorHandling:
    def _make_response(self, status: int, body: dict) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = body
        resp.text = str(body)
        return resp

    def test_rate_limit_429(self) -> None:
        client = _make_client()
        with pytest.raises(RateLimitExceededError):
            client._handle_error_response(
                self._make_response(429, {"code": -1, "msg": "rate limit"})
            )

    def test_auth_error(self) -> None:
        client = _make_client()
        with pytest.raises(AuthenticationError):
            client._handle_error_response(
                self._make_response(401, {"code": -2015, "msg": "Invalid API key"})
            )

    def test_insufficient_balance(self) -> None:
        client = _make_client()
        with pytest.raises(InsufficientBalanceError):
            client._handle_error_response(
                self._make_response(400, {"code": -2010, "msg": "Account has insufficient balance"})
            )

    def test_order_not_found(self) -> None:
        client = _make_client()
        with pytest.raises(OrderNotFoundError):
            client._handle_error_response(
                self._make_response(400, {"code": -2013, "msg": "Order does not exist"})
            )

    def test_order_rejected(self) -> None:
        client = _make_client()
        with pytest.raises(OrderRejectedError):
            client._handle_error_response(
                self._make_response(400, {"code": -1013, "msg": "Filter failure"})
            )

    def test_cancel_requires_id(self) -> None:
        client = _make_client()
        with pytest.raises(InvalidOrderError, match="order_id or client_order_id"):
            import asyncio
            asyncio.run(client.cancel_order(symbol="BTCUSDT"))


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


class TestBinanceClientConstruction:
    def test_default_url(self) -> None:
        client = BinanceRESTClient(_make_creds())
        assert "api.binance.com" in client._base_url

    def test_testnet_url(self) -> None:
        client = BinanceRESTClient(_make_creds(), testnet=True)
        assert "testnet" in client._base_url

    def test_custom_url(self) -> None:
        client = BinanceRESTClient(_make_creds(), base_url="https://custom.api")
        assert client._base_url == "https://custom.api"

    def test_exchange_name(self) -> None:
        client = _make_client()
        assert client._exchange_name == "binance"
