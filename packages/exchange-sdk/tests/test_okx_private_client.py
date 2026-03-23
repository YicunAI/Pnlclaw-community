"""Tests for OKXPrivateWSClient and OKXPrivateNormalizer."""

from __future__ import annotations

import pytest

from pnlclaw_exchange.exchanges.okx.private_client import OKXPrivateNormalizer
from pnlclaw_types.trading import OrderSide


@pytest.fixture
def normalizer() -> OKXPrivateNormalizer:
    return OKXPrivateNormalizer()


class TestOKXPrivateNormalizer:
    def test_normalize_order(self, normalizer: OKXPrivateNormalizer) -> None:
        item = {
            "instId": "BTC-USDT",
            "ordId": "678901",
            "clOrdId": "myOrdId",
            "side": "buy",
            "ordType": "limit",
            "state": "filled",
            "sz": "0.01",
            "accFillSz": "0.01",
            "avgPx": "67000",
            "fillPx": "67000",
            "fillSz": "0.01",
            "fee": "-0.067",
            "feeCcy": "USDT",
            "uTime": "1711000000000",
        }
        result = normalizer.normalize_order(item)

        assert result.exchange == "okx"
        assert result.exchange_order_id == "678901"
        assert result.client_order_id == "myOrdId"
        assert result.symbol == "BTC/USDT"
        assert result.side == OrderSide.BUY
        assert result.status == "FILLED"
        assert result.filled_quantity == 0.01
        assert result.avg_fill_price == 67000.0
        assert result.commission == 0.067
        assert result.raw == item

    def test_normalize_order_sell(self, normalizer: OKXPrivateNormalizer) -> None:
        item = {
            "instId": "ETH-USDT",
            "ordId": "111",
            "side": "sell",
            "ordType": "market",
            "state": "partially_filled",
            "sz": "1.0",
            "accFillSz": "0.5",
            "avgPx": "3500",
            "fillPx": "3500",
            "fillSz": "0.5",
            "fee": "-0.175",
            "feeCcy": "USDT",
            "uTime": "1711000000000",
        }
        result = normalizer.normalize_order(item)

        assert result.side == OrderSide.SELL
        assert result.status == "PARTIALLY_FILLED"
        assert result.filled_quantity == 0.5

    def test_normalize_account(self, normalizer: OKXPrivateNormalizer) -> None:
        item = {
            "details": [
                {"ccy": "BTC", "availBal": "0.5", "frozenBal": "0.1"},
                {"ccy": "USDT", "availBal": "10000", "frozenBal": "0"},
            ],
        }
        result = normalizer.normalize_account(item, ts=1711000000000)

        assert len(result) == 2
        assert result[0].asset == "BTC"
        assert result[0].free == 0.5
        assert result[0].locked == 0.1
        assert result[1].asset == "USDT"
        assert result[1].free == 10000.0


class TestOKXPrivateWSClient:
    def test_client_instantiation(self) -> None:
        from pnlclaw_exchange.exchanges.okx.private_client import OKXPrivateWSClient

        client = OKXPrivateWSClient(
            api_key="test",
            api_secret="test",
            passphrase="test",
        )
        assert client.config.exchange == "okx"
        assert not client.is_connected
