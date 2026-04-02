"""Tests for OKX normalizer."""

from pnlclaw_exchange.exchanges.okx.normalizer import OKXNormalizer, _okx_symbol_to_unified


class TestOKXSymbolConversion:
    def test_basic(self) -> None:
        assert _okx_symbol_to_unified("BTC-USDT") == "BTC/USDT"
        assert _okx_symbol_to_unified("ETH-USDC") == "ETH/USDC"

    def test_triple_part(self) -> None:
        # SWAP suffix is stripped — unified format is always BASE/QUOTE
        assert _okx_symbol_to_unified("BTC-USDT-SWAP") == "BTC/USDT"


class TestOKXNormalizeTicker:
    def test_basic_ticker(self) -> None:
        norm = OKXNormalizer()
        data = {
            "instType": "SPOT",
            "instId": "BTC-USDT",
            "last": "70550.5",
            "lastSz": "0.1",
            "askPx": "70551.0",
            "askSz": "11",
            "bidPx": "70550.0",
            "bidSz": "5",
            "open24h": "69000",
            "high24h": "71000",
            "low24h": "68500",
            "vol24h": "12345",
            "ts": "1700000000000",
        }
        event = norm.normalize_ticker(data, "BTC-USDT")
        assert event.exchange == "okx"
        assert event.symbol == "BTC/USDT"
        assert event.last_price == 70550.5
        assert event.bid == 70550.0
        assert event.ask == 70551.0
        assert event.volume_24h == 12345.0
        assert event.timestamp == 1700000000000
        assert event.change_24h_pct > 0  # price went up from 69000

    def test_zero_open_no_crash(self) -> None:
        norm = OKXNormalizer()
        data = {
            "last": "100.0",
            "askPx": "101",
            "bidPx": "99",
            "open24h": "0",
            "vol24h": "50",
            "ts": "1700000000000",
        }
        event = norm.normalize_ticker(data, "ETH-USDT")
        assert event.change_24h_pct == 0.0


class TestOKXNormalizeCandle:
    def test_basic_candle(self) -> None:
        norm = OKXNormalizer()
        candle = [
            "1700000000000",  # ts
            "70000.0",  # open
            "71000.0",  # high
            "69000.0",  # low
            "70500.0",  # close
            "1234.5",  # vol
            "86000000",  # volCcy
            "86000000",  # volCcyQuote
            "1",  # confirm (closed)
        ]
        event = norm.normalize_candle(candle, "BTC-USDT", "candle1H")
        assert event.exchange == "okx"
        assert event.symbol == "BTC/USDT"
        assert event.interval == "1h"
        assert event.open == 70000.0
        assert event.high == 71000.0
        assert event.close == 70500.0
        assert event.volume == 1234.5
        assert event.closed is True

    def test_not_closed(self) -> None:
        norm = OKXNormalizer()
        candle = ["1700000000000", "100", "110", "90", "105", "50", "5000", "5000", "0"]
        event = norm.normalize_candle(candle, "ETH-USDT", "candle1D")
        assert event.closed is False
        assert event.interval == "1d"

    def test_minute_interval(self) -> None:
        norm = OKXNormalizer()
        candle = ["1700000000000", "100", "110", "90", "105", "50", "5000", "5000", "1"]
        event = norm.normalize_candle(candle, "ETH-USDT", "candle5m")
        assert event.interval == "5m"
