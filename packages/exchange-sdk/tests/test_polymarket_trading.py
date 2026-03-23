"""Tests for the Polymarket CLOB trading client."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pnlclaw_exchange.exchanges.polymarket.trading import (
    PolymarketCredentials,
    PolymarketOrderType,
    PolymarketSide,
    PolymarketTradingClient,
)
from pnlclaw_exchange.exceptions import (
    InvalidOrderError,
)


def _make_creds() -> PolymarketCredentials:
    return PolymarketCredentials(
        api_key="test-key",
        api_secret="test-secret",
        api_passphrase="test-pass",
        wallet_address="0xTestAddress",
    )


def _make_client() -> PolymarketTradingClient:
    return PolymarketTradingClient(
        _make_creds(), base_url="https://clob.polymarket.com"
    )


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


class TestPolymarketCredentials:
    def test_creation(self) -> None:
        creds = _make_creds()
        assert creds.api_key == "test-key"
        assert creds.wallet_address == "0xTestAddress"


# ---------------------------------------------------------------------------
# Auth headers
# ---------------------------------------------------------------------------


class TestPolymarketAuth:
    def test_auth_headers_have_all_fields(self) -> None:
        client = _make_client()
        headers = client._build_auth_headers("POST", "/order", '{"tokenID":"abc"}')
        assert "POLY-API-KEY" in headers
        assert "POLY-SIGNATURE" in headers
        assert "POLY-TIMESTAMP" in headers
        assert "POLY-ADDRESS" in headers
        assert "POLY-PASSPHRASE" in headers
        assert headers["POLY-API-KEY"] == "test-key"

    def test_signature_changes_with_body(self) -> None:
        client = _make_client()
        h1 = client._build_auth_headers("POST", "/order", '{"a":1}')
        h2 = client._build_auth_headers("POST", "/order", '{"b":2}')
        assert h1["POLY-SIGNATURE"] != h2["POLY-SIGNATURE"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestPolymarketOrderValidation:
    @pytest.mark.asyncio
    async def test_price_must_be_between_0_and_1(self) -> None:
        client = _make_client()
        with pytest.raises(InvalidOrderError, match="between 0.01 and 0.99"):
            await client.place_order(
                token_id="abc", side="BUY", price=1.5, size=10,
            )

    @pytest.mark.asyncio
    async def test_price_zero_invalid(self) -> None:
        client = _make_client()
        with pytest.raises(InvalidOrderError):
            await client.place_order(
                token_id="abc", side="BUY", price=0, size=10,
            )

    @pytest.mark.asyncio
    async def test_size_must_be_positive(self) -> None:
        client = _make_client()
        with pytest.raises(InvalidOrderError, match="positive"):
            await client.place_order(
                token_id="abc", side="BUY", price=0.5, size=-1,
            )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestPolymarketEnums:
    def test_order_types(self) -> None:
        assert PolymarketOrderType.GTC == "GTC"
        assert PolymarketOrderType.FOK == "FOK"
        assert PolymarketOrderType.GTD == "GTD"

    def test_sides(self) -> None:
        assert PolymarketSide.BUY == "BUY"
        assert PolymarketSide.SELL == "SELL"
