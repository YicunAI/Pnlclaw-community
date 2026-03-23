"""Polymarket WebSocket client for real-time market data and user events.

Supports three channels:
- **Market Channel** (public): orderbook updates, price changes, last trade
- **User Channel** (authenticated): order status, trade lifecycle events
- **Live Data Socket**: all events + market creation/resolution, comments, crypto

Endpoints:
    wss://ws-subscriptions-clob.polymarket.com/ws/market
    wss://ws-subscriptions-clob.polymarket.com/ws/user
    wss://ws-subscriptions-clob.polymarket.com/ws/rtds

Docs: https://docs.polymarket.com/market-data/websocket/overview
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from enum import Enum
from typing import Any

import websockets
import websockets.asyncio.client

from pnlclaw_exchange.base.stall_watchdog import StallTimeoutMeta, StallWatchdog
from pnlclaw_exchange.base.ws_client import BaseWSClient
from pnlclaw_exchange.types import WSClientConfig

logger = logging.getLogger(__name__)

POLYMARKET_WS_MARKET = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
POLYMARKET_WS_USER = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
POLYMARKET_WS_LIVE = "wss://ws-subscriptions-clob.polymarket.com/ws/rtds"


class PolymarketEventType(str, Enum):
    """Polymarket WebSocket event types."""

    # Market channel
    BOOK = "book"
    PRICE_CHANGE = "price_change"
    LAST_TRADE_PRICE = "last_trade_price"
    TICK_SIZE_CHANGE = "tick_size_change"

    # User channel
    ORDER = "order"
    TRADE = "trade"

    # Live data
    MARKET_CREATED = "market_created"
    MARKET_RESOLVED = "market_resolved"
    TRADES = "trades"
    ORDERS_MATCHED = "orders_matched"


class PolymarketTradeStatus(str, Enum):
    """Lifecycle states for a Polymarket trade."""

    MATCHED = "MATCHED"
    MINED = "MINED"
    CONFIRMED = "CONFIRMED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"


class PolymarketOrderEventType(str, Enum):
    """Order event sub-types on the user channel."""

    PLACEMENT = "PLACEMENT"
    UPDATE = "UPDATE"
    CANCELLATION = "CANCELLATION"


class PolymarketWSClient(BaseWSClient):
    """Polymarket WebSocket client for market data and user events.

    Manages up to two concurrent WebSocket connections:
    - **Market socket** for public orderbook/price data (no auth)
    - **User socket** for authenticated order/trade events

    Usage::

        ws = PolymarketWSClient(
            on_book=lambda data: print("Book:", data),
            on_order=lambda data: print("Order:", data),
            on_trade=lambda data: print("Trade:", data),
        )
        await ws.connect()

        # Subscribe to public market data for specific tokens
        await ws.subscribe_market(["token_id_1", "token_id_2"])

        # Subscribe to authenticated user channel (requires credentials)
        await ws.subscribe_user(
            api_key="...", api_secret="...", api_passphrase="...",
            markets=["condition_id_1"],
        )

        # ... run event loop ...

        await ws.close()
    """

    def __init__(
        self,
        *,
        market_url: str = POLYMARKET_WS_MARKET,
        user_url: str = POLYMARKET_WS_USER,
        stall_timeout_s: float = 60.0,
        on_book: Callable[[dict[str, Any]], Any] | None = None,
        on_price_change: Callable[[dict[str, Any]], Any] | None = None,
        on_last_trade: Callable[[dict[str, Any]], Any] | None = None,
        on_order: Callable[[dict[str, Any]], Any] | None = None,
        on_trade: Callable[[dict[str, Any]], Any] | None = None,
        on_stall: Callable[[StallTimeoutMeta], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        config = WSClientConfig(url=market_url, exchange="polymarket")
        super().__init__(config, **kwargs)

        self._market_url = market_url
        self._user_url = user_url

        self._ws_market: websockets.asyncio.client.ClientConnection | None = None
        self._ws_user: websockets.asyncio.client.ClientConnection | None = None
        self._recv_market_task: asyncio.Task[None] | None = None
        self._recv_user_task: asyncio.Task[None] | None = None

        self._stall_watchdog = StallWatchdog(
            timeout_s=stall_timeout_s,
            on_timeout=on_stall or self._default_stall_handler,
            label="polymarket-ws-stall",
        )

        # Typed callbacks
        self.on_book = on_book
        self.on_price_change = on_price_change
        self.on_last_trade = on_last_trade
        self.on_order = on_order
        self.on_trade = on_trade

        self._user_authenticated = False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the market WebSocket connection.

        The user socket is connected lazily when :meth:`subscribe_user`
        is called, since it requires API credentials.
        """
        logger.info("Connecting to Polymarket market WS: %s", self._market_url)
        self._ws_market = await websockets.asyncio.client.connect(self._market_url)

        await self._dispatch_connect()
        await self._stall_watchdog.start()
        self._stall_watchdog.arm()

        self._recv_market_task = asyncio.create_task(
            self._receive_loop(self._ws_market, "market"),
            name="polymarket-ws-market-recv",
        )

    async def _connect_user(self) -> None:
        """Open the user WebSocket connection (called by subscribe_user)."""
        if self._ws_user is not None:
            return
        logger.info("Connecting to Polymarket user WS: %s", self._user_url)
        self._ws_user = await websockets.asyncio.client.connect(self._user_url)
        self._recv_user_task = asyncio.create_task(
            self._receive_loop(self._ws_user, "user"),
            name="polymarket-ws-user-recv",
        )

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    async def subscribe(self, streams: list[str]) -> None:
        """Subscribe to market channels by asset/token IDs.

        Args:
            streams: List of token IDs to subscribe to.
        """
        await self.subscribe_market(streams)

    async def subscribe_market(self, token_ids: list[str]) -> None:
        """Subscribe to public market data for specific tokens.

        Receives: orderbook updates, price changes, last trade price.

        Args:
            token_ids: Polymarket token IDs (long hex strings).
        """
        if not token_ids or self._ws_market is None:
            return

        self._subscriptions.update(f"market:{tid}" for tid in token_ids)

        msg = {
            "assets_ids": token_ids,
            "type": "market",
        }
        await self._ws_market.send(json.dumps(msg))
        logger.info("Polymarket market subscribe: %d tokens", len(token_ids))

    async def subscribe_user(
        self,
        *,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        markets: list[str] | None = None,
    ) -> None:
        """Subscribe to authenticated user channel for order/trade events.

        Receives: order placements/updates/cancellations, trade lifecycle.

        Args:
            api_key: Polymarket CLOB API key.
            api_secret: Polymarket CLOB API secret.
            api_passphrase: Polymarket CLOB API passphrase.
            markets: Optional list of condition IDs to filter. If None,
                     receives events for all markets.
        """
        await self._connect_user()
        if self._ws_user is None:
            return

        msg: dict[str, Any] = {
            "auth": {
                "apiKey": api_key,
                "secret": api_secret,
                "passphrase": api_passphrase,
            },
            "type": "user",
        }
        if markets:
            msg["markets"] = markets

        self._subscriptions.add("user:authenticated")
        if markets:
            for m in markets:
                self._subscriptions.add(f"user:{m}")

        await self._ws_user.send(json.dumps(msg))
        self._user_authenticated = True
        logger.info(
            "Polymarket user subscribe: authenticated, markets=%s",
            markets or "all",
        )

    async def unsubscribe(self, streams: list[str]) -> None:
        """Unsubscribe from streams.

        Note: Polymarket WS does not support granular unsubscribe for
        the user channel. Closing the connection is the recommended approach.
        For the market channel, individual token unsubscription is supported.
        """
        self._subscriptions -= set(streams)

        market_tokens = [
            s.split(":", 1)[1] for s in streams
            if s.startswith("market:")
        ]
        if market_tokens and self._ws_market is not None:
            msg = {
                "assets_ids": market_tokens,
                "type": "unsubscribe",
            }
            await self._ws_market.send(json.dumps(msg))
            logger.info("Polymarket market unsubscribe: %d tokens", len(market_tokens))

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close all WebSocket connections."""
        self._stall_watchdog.stop()

        for task in (self._recv_market_task, self._recv_user_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._recv_market_task = None
        self._recv_user_task = None

        for ws in (self._ws_market, self._ws_user):
            if ws is not None:
                try:
                    await ws.close()
                except Exception:
                    pass
        self._ws_market = None
        self._ws_user = None
        self._user_authenticated = False

        await self._dispatch_disconnect(code=1000, reason="client close")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_user_authenticated(self) -> bool:
        """Whether the user channel is authenticated and active."""
        return self._user_authenticated and self._ws_user is not None

    # ------------------------------------------------------------------
    # Receive loop & routing
    # ------------------------------------------------------------------

    async def _receive_loop(
        self,
        ws: websockets.asyncio.client.ClientConnection,
        label: str,
    ) -> None:
        """Read messages from one WebSocket and route them."""
        try:
            async for raw in ws:
                try:
                    data: dict[str, Any] = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning(
                        "Invalid JSON from Polymarket %s: %s", label, str(raw)[:200]
                    )
                    continue
                await self._route_message(data, label)
        except websockets.ConnectionClosed as exc:
            logger.info("Polymarket %s WS closed: %s", label, exc)
            if label == "user":
                self._user_authenticated = False
            await self._dispatch_disconnect(
                code=getattr(exc, "code", 1006), reason=str(exc)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Error in Polymarket %s receive loop: %s", label, exc)
            await self._dispatch_error(exc)

    async def _route_message(self, data: dict[str, Any], channel: str) -> None:
        """Route a parsed Polymarket WebSocket message to the appropriate callback."""
        self._stall_watchdog.touch()
        await self._dispatch_message(data)

        event_type = data.get("event_type", data.get("type", ""))

        if channel == "market":
            await self._route_market_event(data, event_type)
        elif channel == "user":
            await self._route_user_event(data, event_type)

    async def _route_market_event(self, data: dict[str, Any], event_type: str) -> None:
        """Route market channel events."""
        if event_type == PolymarketEventType.BOOK:
            await self._invoke(self.on_book, data)
        elif event_type == PolymarketEventType.PRICE_CHANGE:
            await self._invoke(self.on_price_change, data)
        elif event_type == PolymarketEventType.LAST_TRADE_PRICE:
            await self._invoke(self.on_last_trade, data)

    async def _route_user_event(self, data: dict[str, Any], event_type: str) -> None:
        """Route user channel events (orders and trades)."""
        if event_type == PolymarketEventType.ORDER:
            await self._invoke(self.on_order, data)
        elif event_type == PolymarketEventType.TRADE:
            await self._invoke(self.on_trade, data)

    # ------------------------------------------------------------------
    # Stall handling
    # ------------------------------------------------------------------

    async def _default_stall_handler(self, meta: StallTimeoutMeta) -> None:
        """Default stall handler: log and close for reconnect."""
        logger.warning(
            "Polymarket WS stall detected (idle %.1fs). Closing for reconnect.",
            meta.idle_s,
        )
        for ws in (self._ws_market, self._ws_user):
            if ws is not None:
                try:
                    await ws.close()
                except Exception:
                    pass
