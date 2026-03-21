"""Tests for SymbolNormalizer."""

from __future__ import annotations

import pytest

from pnlclaw_types.errors import ValidationError

from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer


@pytest.fixture
def normalizer() -> SymbolNormalizer:
    return SymbolNormalizer()


class TestToUnified:
    def test_btcusdt(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_unified("binance", "BTCUSDT") == "BTC/USDT"

    def test_ethbtc(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_unified("binance", "ETHBTC") == "ETH/BTC"

    def test_solusdt(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_unified("binance", "SOLUSDT") == "SOL/USDT"

    def test_btcfdusd(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_unified("binance", "BTCFDUSD") == "BTC/FDUSD"

    def test_bnbeth(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_unified("binance", "BNBETH") == "BNB/ETH"

    def test_lowercase_input(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_unified("binance", "btcusdt") == "BTC/USDT"

    def test_usdc_pair(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_unified("binance", "ETHUSDC") == "ETH/USDC"

    def test_unknown_quote_raises(self, normalizer: SymbolNormalizer) -> None:
        with pytest.raises(ValidationError):
            normalizer.to_unified("binance", "XYZABC")


class TestToExchange:
    def test_btc_usdt(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_exchange("binance", "BTC/USDT") == "BTCUSDT"

    def test_eth_btc(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_exchange("binance", "ETH/BTC") == "ETHBTC"

    def test_passthrough_without_slash(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_exchange("binance", "BTCUSDT") == "BTCUSDT"

    def test_lowercase_input(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_exchange("binance", "btc/usdt") == "BTCUSDT"


class TestRegistry:
    def test_unknown_exchange_raises(self, normalizer: SymbolNormalizer) -> None:
        with pytest.raises(ValidationError, match="No symbol rule"):
            normalizer.to_unified("unknown_exchange", "BTCUSDT")

    def test_case_insensitive_exchange(self, normalizer: SymbolNormalizer) -> None:
        assert normalizer.to_unified("Binance", "BTCUSDT") == "BTC/USDT"
        assert normalizer.to_unified("BINANCE", "BTCUSDT") == "BTC/USDT"

    def test_register_custom_rule(self, normalizer: SymbolNormalizer) -> None:
        class OKXRule:
            def to_unified(self, raw_symbol: str) -> str:
                return raw_symbol.replace("-", "/")

            def to_exchange(self, unified_symbol: str) -> str:
                return unified_symbol.replace("/", "-")

        normalizer.register("okx", OKXRule())
        assert normalizer.to_unified("okx", "BTC-USDT") == "BTC/USDT"
        assert normalizer.to_exchange("okx", "BTC/USDT") == "BTC-USDT"
