"""Tests for Polymarket CLOB client with mocked HTTP responses."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from pnlclaw_exchange.exchanges.polymarket.client import PolymarketClient
from pnlclaw_exchange.exchanges.polymarket.models import (
    PolymarketMarket,
    PolymarketOrderBook,
)


def _mock_response(data: dict | list, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.text = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
    resp.raise_for_status = MagicMock()
    return resp


class TestPolymarketListMarkets:
    @pytest.mark.asyncio
    async def test_parse_markets(self) -> None:
        client = PolymarketClient()
        raw_markets = [
            {
                "condition_id": "0xabc",
                "question_id": "0xdef",
                "question": "Will BTC reach $100k?",
                "description": "Test market",
                "market_slug": "btc-100k",
                "active": True,
                "closed": False,
                "tokens": [
                    {"token_id": "0x111", "outcome": "Yes", "price": 0.65},
                    {"token_id": "0x222", "outcome": "No", "price": 0.35},
                ],
                "volume": 500000,
                "volume_num_24hr": 12000,
                "liquidity": 80000,
            }
        ]
        client._http = MagicMock()
        client._http.get = AsyncMock(return_value=_mock_response(raw_markets))

        markets = await client.list_markets(limit=1)

        assert len(markets) == 1
        m = markets[0]
        assert isinstance(m, PolymarketMarket)
        assert m.question == "Will BTC reach $100k?"
        assert len(m.tokens) == 2
        assert m.tokens[0].outcome == "Yes"
        assert m.tokens[0].price == 0.65
        assert m.volume == 500000
        assert m.volume_24h == 12000


class TestPolymarketOrderBook:
    @pytest.mark.asyncio
    async def test_parse_orderbook(self) -> None:
        client = PolymarketClient()
        raw_book = {
            "market": "0xabc",
            "asset_id": "0x111",
            "timestamp": "1700000000",
            "bids": [
                {"price": "0.64", "size": "100"},
                {"price": "0.63", "size": "200"},
            ],
            "asks": [
                {"price": "0.66", "size": "150"},
                {"price": "0.67", "size": "250"},
            ],
            "last_trade_price": "0.65",
            "tick_size": "0.01",
            "min_order_size": "5",
        }
        client._http = MagicMock()
        client._http.get = AsyncMock(return_value=_mock_response(raw_book))

        book = await client.get_orderbook("0x111")

        assert isinstance(book, PolymarketOrderBook)
        assert book.asset_id == "0x111"
        assert len(book.bids) == 2
        assert len(book.asks) == 2
        assert book.bids[0]["price"] == "0.64"
        assert book.last_trade_price == "0.65"


class TestPolymarketPrices:
    @pytest.mark.asyncio
    async def test_get_midpoint(self) -> None:
        client = PolymarketClient()
        client._http = MagicMock()
        client._http.get = AsyncMock(return_value=_mock_response({"mid": "0.65"}))

        mid = await client.get_midpoint("0x111")
        assert mid == 0.65

    @pytest.mark.asyncio
    async def test_get_price(self) -> None:
        client = PolymarketClient()
        client._http = MagicMock()
        client._http.get = AsyncMock(return_value=_mock_response({"price": "0.64"}))

        price = await client.get_price("0x111", side="BUY")
        assert price == 0.64

    @pytest.mark.asyncio
    async def test_get_last_trade_price(self) -> None:
        client = PolymarketClient()
        client._http = MagicMock()
        client._http.get = AsyncMock(return_value=_mock_response({"price": "0.65", "side": "BUY"}))

        result = await client.get_last_trade_price("0x111")
        assert result.price == 0.65
        assert result.side == "BUY"


class TestPolymarketServerTime:
    @pytest.mark.asyncio
    async def test_get_server_time(self) -> None:
        client = PolymarketClient()
        resp = MagicMock()
        resp.text = "1700000000"
        resp.raise_for_status = MagicMock()
        client._http = MagicMock()
        client._http.get = AsyncMock(return_value=resp)

        ts = await client.get_server_time()
        assert ts == 1700000000
