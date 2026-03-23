"""Tests for BinanceNormalizer."""

from __future__ import annotations

from typing import Any

import pytest

from pnlclaw_exchange.exchanges.binance.normalizer import (
    BinanceDepthDelta,
    BinanceNormalizer,
)
from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer
from pnlclaw_types.market import KlineEvent, TickerEvent, TradeEvent


@pytest.fixture
def normalizer() -> BinanceNormalizer:
    return BinanceNormalizer(SymbolNormalizer())


class TestTickerNormalization:
    def test_basic_fields(
        self, normalizer: BinanceNormalizer, sample_binance_ticker: dict[str, Any]
    ) -> None:
        result = normalizer.normalize(sample_binance_ticker)
        assert isinstance(result, TickerEvent)
        assert result.exchange == "binance"
        assert result.symbol == "BTC/USDT"
        assert result.timestamp == 1711000000000
        assert result.last_price == 67000.0
        assert result.bid == 66999.5
        assert result.ask == 67000.5
        assert result.volume_24h == 12345.67
        assert result.change_24h_pct == 2.35


class TestTradeNormalization:
    def test_basic_fields(
        self, normalizer: BinanceNormalizer, sample_binance_trade: dict[str, Any]
    ) -> None:
        result = normalizer.normalize(sample_binance_trade)
        assert isinstance(result, TradeEvent)
        assert result.exchange == "binance"
        assert result.symbol == "BTC/USDT"
        assert result.timestamp == 1711000000000
        assert result.trade_id == "123456789"
        assert result.price == 67000.0
        assert result.quantity == 0.5
        assert result.side == "buy"

    def test_seller_side(self, normalizer: BinanceNormalizer) -> None:
        """When m=True (buyer is maker), the trade side should be 'sell'."""
        data = {
            "e": "trade",
            "E": 1711000000000,
            "s": "BTCUSDT",
            "t": 999,
            "p": "67000.00",
            "q": "1.0",
            "m": True,
        }
        result = normalizer.normalize(data)
        assert isinstance(result, TradeEvent)
        assert result.side == "sell"


class TestKlineNormalization:
    def test_basic_fields(
        self, normalizer: BinanceNormalizer, sample_binance_kline: dict[str, Any]
    ) -> None:
        result = normalizer.normalize(sample_binance_kline)
        assert isinstance(result, KlineEvent)
        assert result.exchange == "binance"
        assert result.symbol == "BTC/USDT"
        assert result.timestamp == 1711000000000
        assert result.interval == "1h"
        assert result.open == 66800.0
        assert result.high == 67200.0
        assert result.low == 66700.0
        assert result.close == 67000.0
        assert result.volume == 1234.56
        assert result.closed is True


class TestDepthNormalization:
    def test_basic_fields(
        self, normalizer: BinanceNormalizer, sample_binance_depth_update: dict[str, Any]
    ) -> None:
        result = normalizer.normalize(sample_binance_depth_update)
        assert isinstance(result, BinanceDepthDelta)
        assert result.first_update_id == 100001
        assert result.last_update_id == 100002
        assert result.delta.exchange == "binance"
        assert result.delta.symbol == "BTC/USDT"
        assert result.delta.sequence_id == 100002
        assert len(result.delta.bids) == 2
        assert len(result.delta.asks) == 2
        assert result.delta.bids[0].price == 66999.0
        assert result.delta.bids[0].quantity == 2.5

    def test_empty_sides(self, normalizer: BinanceNormalizer) -> None:
        data = {
            "e": "depthUpdate",
            "E": 1711000000000,
            "s": "BTCUSDT",
            "U": 1,
            "u": 2,
            "b": [],
            "a": [],
        }
        result = normalizer.normalize(data)
        assert isinstance(result, BinanceDepthDelta)
        assert len(result.delta.bids) == 0
        assert len(result.delta.asks) == 0


class TestUnknownEvent:
    def test_returns_none(self, normalizer: BinanceNormalizer) -> None:
        result = normalizer.normalize({"e": "unknownEvent", "s": "BTCUSDT"})
        assert result is None

    def test_missing_event_type(self, normalizer: BinanceNormalizer) -> None:
        result = normalizer.normalize({"data": "something"})
        assert result is None
