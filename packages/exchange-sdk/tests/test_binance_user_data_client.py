"""Tests for BinanceUserDataClient and BinanceUserDataNormalizer."""

from __future__ import annotations

import pytest

from pnlclaw_exchange.exchanges.binance.user_data_client import (
    BinanceUserDataNormalizer,
)
from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer


@pytest.fixture
def normalizer() -> BinanceUserDataNormalizer:
    return BinanceUserDataNormalizer(SymbolNormalizer())


class TestBinanceUserDataNormalizer:
    def test_normalize_execution_report(self, normalizer: BinanceUserDataNormalizer) -> None:
        data = {
            "e": "executionReport",
            "E": 1711000000000,
            "s": "BTCUSDT",
            "S": "BUY",
            "o": "LIMIT",
            "X": "FILLED",
            "q": "0.001",
            "z": "0.001",
            "Z": "67.0",
            "L": "67000.0",
            "l": "0.001",
            "n": "0.067",
            "N": "USDT",
            "i": 12345,
            "c": "myClientOrderId",
        }
        result = normalizer.normalize_execution_report(data)

        assert result.exchange == "binance"
        assert result.exchange_order_id == "12345"
        assert result.client_order_id == "myClientOrderId"
        assert result.status == "FILLED"
        assert result.filled_quantity == 0.001
        assert result.avg_fill_price == pytest.approx(67000.0)
        assert result.last_fill_price == 67000.0
        assert result.last_fill_quantity == 0.001
        assert result.commission == 0.067
        assert result.commission_asset == "USDT"
        assert result.raw == data

    def test_normalize_account_position(self, normalizer: BinanceUserDataNormalizer) -> None:
        data = {
            "e": "outboundAccountPosition",
            "E": 1711000000000,
            "B": [
                {"a": "BTC", "f": "0.5", "l": "0.1"},
                {"a": "USDT", "f": "10000", "l": "500"},
            ],
        }
        result = normalizer.normalize_account_position(data)

        assert len(result) == 2
        assert result[0].asset == "BTC"
        assert result[0].free == 0.5
        assert result[0].locked == 0.1
        assert result[1].asset == "USDT"
        assert result[1].free == 10000.0

    def test_normalize_balance_update(self, normalizer: BinanceUserDataNormalizer) -> None:
        data = {
            "e": "balanceUpdate",
            "E": 1711000000000,
            "a": "BTC",
            "d": "0.001",
        }
        result = normalizer.normalize_balance_update(data)

        assert result.exchange == "binance"
        assert result.asset == "BTC"
        assert result.free == 0.001


class TestBinanceUserDataClient:
    def test_client_instantiation(self) -> None:
        from pnlclaw_exchange.exchanges.binance.user_data_client import (
            BinanceUserDataClient,
        )

        client = BinanceUserDataClient(
            api_key="test_key",
            api_secret="test_secret",
        )
        assert client.config.exchange == "binance"
        assert not client.is_connected
