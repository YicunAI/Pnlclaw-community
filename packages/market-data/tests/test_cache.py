"""Tests for pnlclaw_market.cache — TTL + LRU cache."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from pnlclaw_market.cache import MarketDataCache, TTLLRUCache


# ---------------------------------------------------------------------------
# TTLLRUCache
# ---------------------------------------------------------------------------


class TestTTLLRUCache:
    """Unit tests for the generic TTL+LRU cache."""

    def test_put_and_get(self) -> None:
        cache: TTLLRUCache[str] = TTLLRUCache(ttl_seconds=10.0, max_size=100)
        cache.put("a", "alpha")
        assert cache.get("a") == "alpha"

    def test_get_missing_key_returns_none(self) -> None:
        cache: TTLLRUCache[str] = TTLLRUCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self) -> None:
        cache: TTLLRUCache[str] = TTLLRUCache(ttl_seconds=0.1, max_size=100)
        cache.put("a", "alpha")
        assert cache.get("a") == "alpha"
        time.sleep(0.15)
        assert cache.get("a") is None

    def test_lru_eviction(self) -> None:
        cache: TTLLRUCache[int] = TTLLRUCache(ttl_seconds=60.0, max_size=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        # Access 'a' to make it recently used
        cache.get("a")
        # Insert 'd' — should evict 'b' (least recently used)
        cache.put("d", 4)
        assert cache.get("b") is None
        assert cache.get("a") == 1
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_put_updates_existing(self) -> None:
        cache: TTLLRUCache[str] = TTLLRUCache(ttl_seconds=10.0, max_size=100)
        cache.put("a", "old")
        cache.put("a", "new")
        assert cache.get("a") == "new"

    def test_remove(self) -> None:
        cache: TTLLRUCache[str] = TTLLRUCache()
        cache.put("a", "alpha")
        assert cache.remove("a") is True
        assert cache.get("a") is None
        assert cache.remove("a") is False

    def test_clear(self) -> None:
        cache: TTLLRUCache[str] = TTLLRUCache()
        cache.put("a", "1")
        cache.put("b", "2")
        cache.clear()
        assert cache.size == 0

    def test_size(self) -> None:
        cache: TTLLRUCache[str] = TTLLRUCache()
        assert cache.size == 0
        cache.put("a", "1")
        assert cache.size == 1

    def test_invalid_ttl_raises(self) -> None:
        with pytest.raises(ValueError, match="ttl_seconds"):
            TTLLRUCache(ttl_seconds=0)

    def test_invalid_max_size_raises(self) -> None:
        with pytest.raises(ValueError, match="max_size"):
            TTLLRUCache(max_size=0)


# ---------------------------------------------------------------------------
# MarketDataCache
# ---------------------------------------------------------------------------


class TestMarketDataCache:
    """Unit tests for the specialized market data cache."""

    def _make_ticker(self, symbol: str = "BTC/USDT", price: float = 67000.0):
        from pnlclaw_types.market import TickerEvent

        return TickerEvent(
            exchange="binance",
            symbol=symbol,
            timestamp=1711000000000,
            last_price=price,
            bid=price - 0.5,
            ask=price + 0.5,
            volume_24h=12345.67,
            change_24h_pct=2.35,
        )

    def _make_kline(self, symbol: str = "BTC/USDT"):
        from pnlclaw_types.market import KlineEvent

        return KlineEvent(
            exchange="binance",
            symbol=symbol,
            timestamp=1711000000000,
            interval="1h",
            open=66800.0,
            high=67200.0,
            low=66700.0,
            close=67000.0,
            volume=1234.56,
            closed=True,
        )

    def test_ticker_put_and_get(self) -> None:
        cache = MarketDataCache()
        ticker = self._make_ticker()
        cache.put_ticker("BTC/USDT", ticker)
        assert cache.get_ticker("BTC/USDT") == ticker

    def test_kline_put_and_get(self) -> None:
        cache = MarketDataCache()
        kline = self._make_kline()
        cache.put_kline("BTC/USDT", kline)
        assert cache.get_kline("BTC/USDT") == kline

    def test_get_missing_returns_none(self) -> None:
        cache = MarketDataCache()
        assert cache.get_ticker("NONE") is None
        assert cache.get_kline("NONE") is None

    def test_clear(self) -> None:
        cache = MarketDataCache()
        cache.put_ticker("BTC/USDT", self._make_ticker())
        cache.put_kline("BTC/USDT", self._make_kline())
        cache.clear()
        assert cache.get_ticker("BTC/USDT") is None
        assert cache.get_kline("BTC/USDT") is None
