"""Tests for the Polymarket WebSocket client."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnlclaw_exchange.exchanges.polymarket.ws_client import (
    POLYMARKET_WS_MARKET,
    POLYMARKET_WS_USER,
    PolymarketEventType,
    PolymarketOrderEventType,
    PolymarketTradeStatus,
    PolymarketWSClient,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestPolymarketEnums:
    def test_event_types(self) -> None:
        assert PolymarketEventType.BOOK == "book"
        assert PolymarketEventType.PRICE_CHANGE == "price_change"
        assert PolymarketEventType.ORDER == "order"
        assert PolymarketEventType.TRADE == "trade"
        assert PolymarketEventType.LAST_TRADE_PRICE == "last_trade_price"
        assert PolymarketEventType.MARKET_CREATED == "market_created"

    def test_trade_statuses(self) -> None:
        assert PolymarketTradeStatus.MATCHED == "MATCHED"
        assert PolymarketTradeStatus.MINED == "MINED"
        assert PolymarketTradeStatus.CONFIRMED == "CONFIRMED"
        assert PolymarketTradeStatus.RETRYING == "RETRYING"
        assert PolymarketTradeStatus.FAILED == "FAILED"

    def test_order_event_types(self) -> None:
        assert PolymarketOrderEventType.PLACEMENT == "PLACEMENT"
        assert PolymarketOrderEventType.UPDATE == "UPDATE"
        assert PolymarketOrderEventType.CANCELLATION == "CANCELLATION"


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


class TestPolymarketWSClientConstruction:
    def test_default_urls(self) -> None:
        ws = PolymarketWSClient()
        assert ws._market_url == POLYMARKET_WS_MARKET
        assert ws._user_url == POLYMARKET_WS_USER

    def test_custom_urls(self) -> None:
        ws = PolymarketWSClient(
            market_url="wss://custom/market", user_url="wss://custom/user"
        )
        assert ws._market_url == "wss://custom/market"
        assert ws._user_url == "wss://custom/user"

    def test_exchange_name(self) -> None:
        ws = PolymarketWSClient()
        assert ws.config.exchange == "polymarket"

    def test_not_authenticated_initially(self) -> None:
        ws = PolymarketWSClient()
        assert ws.is_user_authenticated is False

    def test_callbacks_assigned(self) -> None:
        cb = MagicMock()
        ws = PolymarketWSClient(
            on_book=cb, on_order=cb, on_trade=cb
        )
        assert ws.on_book is cb
        assert ws.on_order is cb
        assert ws.on_trade is cb


# ---------------------------------------------------------------------------
# Message routing
# ---------------------------------------------------------------------------


class TestPolymarketMessageRouting:
    def _make_ws(self) -> PolymarketWSClient:
        ws = PolymarketWSClient()
        ws.on_book = AsyncMock()
        ws.on_price_change = AsyncMock()
        ws.on_last_trade = AsyncMock()
        ws.on_order = AsyncMock()
        ws.on_trade = AsyncMock()
        ws._stall_watchdog = MagicMock()
        ws._stall_watchdog.touch = MagicMock()
        return ws

    @pytest.mark.asyncio
    async def test_route_book_event(self) -> None:
        ws = self._make_ws()
        data = {
            "event_type": "book",
            "asset_id": "abc123",
            "bids": [["0.55", "100"]],
            "asks": [["0.56", "200"]],
        }
        await ws._route_message(data, "market")
        ws.on_book.assert_awaited_once_with(data)

    @pytest.mark.asyncio
    async def test_route_price_change(self) -> None:
        ws = self._make_ws()
        data = {"event_type": "price_change", "asset_id": "abc123", "price": "0.57"}
        await ws._route_message(data, "market")
        ws.on_price_change.assert_awaited_once_with(data)

    @pytest.mark.asyncio
    async def test_route_last_trade_price(self) -> None:
        ws = self._make_ws()
        data = {"event_type": "last_trade_price", "asset_id": "abc123", "price": "0.58"}
        await ws._route_message(data, "market")
        ws.on_last_trade.assert_awaited_once_with(data)

    @pytest.mark.asyncio
    async def test_route_order_event(self) -> None:
        ws = self._make_ws()
        data = {
            "event_type": "order",
            "id": "order-001",
            "asset_id": "abc123",
            "side": "BUY",
            "price": "0.55",
            "original_size": "10",
            "size_matched": "0",
            "type": "PLACEMENT",
            "market": "0xcondition",
            "owner": "0xowner",
        }
        await ws._route_message(data, "user")
        ws.on_order.assert_awaited_once_with(data)

    @pytest.mark.asyncio
    async def test_route_trade_event(self) -> None:
        ws = self._make_ws()
        data = {
            "event_type": "trade",
            "id": "trade-001",
            "asset_id": "abc123",
            "side": "BUY",
            "price": "0.55",
            "size": "10",
            "status": "MATCHED",
            "market": "0xcondition",
            "owner": "0xowner",
        }
        await ws._route_message(data, "user")
        ws.on_trade.assert_awaited_once_with(data)

    @pytest.mark.asyncio
    async def test_market_events_not_routed_to_user(self) -> None:
        ws = self._make_ws()
        data = {"event_type": "book", "asset_id": "abc"}
        await ws._route_message(data, "market")
        ws.on_order.assert_not_awaited()
        ws.on_trade.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_events_not_routed_to_market(self) -> None:
        ws = self._make_ws()
        data = {"event_type": "order", "id": "o1"}
        await ws._route_message(data, "user")
        ws.on_book.assert_not_awaited()
        ws.on_price_change.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_event_no_crash(self) -> None:
        ws = self._make_ws()
        data = {"event_type": "unknown_type", "data": "something"}
        await ws._route_message(data, "market")
        ws.on_book.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stall_watchdog_touched(self) -> None:
        ws = self._make_ws()
        data = {"event_type": "book", "asset_id": "abc"}
        await ws._route_message(data, "market")
        ws._stall_watchdog.touch.assert_called_once()


# ---------------------------------------------------------------------------
# Subscription tracking
# ---------------------------------------------------------------------------


class TestPolymarketSubscriptions:
    def test_subscribe_market_tracks_subscriptions(self) -> None:
        ws = PolymarketWSClient()
        ws._ws_market = AsyncMock()
        ws._ws_market.send = AsyncMock()

        asyncio.run(ws.subscribe_market(["token1", "token2"]))
        assert "market:token1" in ws._subscriptions
        assert "market:token2" in ws._subscriptions
        assert ws._ws_market.send.call_count >= 1

    def test_unsubscribe_removes_from_tracking(self) -> None:
        ws = PolymarketWSClient()
        ws._subscriptions.add("market:token1")
        ws._subscriptions.add("market:token2")
        ws._ws_market = AsyncMock()
        ws._ws_market.send = AsyncMock()

        asyncio.run(ws.unsubscribe(["market:token1"]))
        assert "market:token1" not in ws._subscriptions
        assert "market:token2" in ws._subscriptions

    def test_subscribe_convenience_method(self) -> None:
        ws = PolymarketWSClient()
        ws._ws_market = AsyncMock()
        ws._ws_market.send = AsyncMock()

        asyncio.run(ws.subscribe(["token_a"]))
        assert "market:token_a" in ws._subscriptions


# ---------------------------------------------------------------------------
# User auth subscription message
# ---------------------------------------------------------------------------


class TestPolymarketUserSubscription:
    def test_user_subscribe_sends_auth(self) -> None:
        ws = PolymarketWSClient()
        ws._ws_user = AsyncMock()
        ws._ws_user.send = AsyncMock()

        asyncio.run(
            ws.subscribe_user(
                api_key="key", api_secret="secret", api_passphrase="pass",
                markets=["0xcondition1"],
            )
        )

        call_args = ws._ws_user.send.call_args[0][0]
        msg = json.loads(call_args)
        assert msg["type"] == "user"
        assert msg["auth"]["apiKey"] == "key"
        assert msg["auth"]["secret"] == "secret"
        assert msg["auth"]["passphrase"] == "pass"
        assert msg["markets"] == ["0xcondition1"]
        assert ws._user_authenticated is True
        assert "user:authenticated" in ws._subscriptions
        assert "user:0xcondition1" in ws._subscriptions

    def test_user_subscribe_no_markets(self) -> None:
        ws = PolymarketWSClient()
        ws._ws_user = AsyncMock()
        ws._ws_user.send = AsyncMock()

        asyncio.run(
            ws.subscribe_user(
                api_key="k", api_secret="s", api_passphrase="p",
            )
        )

        call_args = ws._ws_user.send.call_args[0][0]
        msg = json.loads(call_args)
        assert "markets" not in msg
        assert ws._user_authenticated is True


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------


class TestPolymarketWSClose:
    @pytest.mark.asyncio
    async def test_close_resets_state(self) -> None:
        ws = PolymarketWSClient()
        ws._ws_market = AsyncMock()
        ws._ws_user = AsyncMock()
        ws._user_authenticated = True
        ws._stall_watchdog = MagicMock()
        ws._stall_watchdog.stop = MagicMock()

        await ws.close()

        assert ws._ws_market is None
        assert ws._ws_user is None
        assert ws._user_authenticated is False
        assert ws.is_connected is False
