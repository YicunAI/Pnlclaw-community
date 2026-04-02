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

Keepalive: Polymarket requires a text ``"PING"`` every 50 seconds.
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

PING_INTERVAL_S = 50  # Polymarket docs: send "PING" every 50 seconds


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

    Keepalive: sends ``"PING"`` text every 50 s per Polymarket docs.
    Auto-reconnect: configurable via ``auto_reconnect``.

    Usage::

        ws = PolymarketWSClient(
            on_book=lambda data: print("Book:", data),
            on_order=lambda data: print("Order:", data),
            on_trade=lambda data: print("Trade:", data),
        )
        await ws.connect()

        # Subscribe to public market data for specific tokens
        await ws.subscribe_market(["token_id_1", "token_id_2"])

        # ... run event loop ...

        await ws.close()
    """

    def __init__(
        self,
        *,
        market_url: str = POLYMARKET_WS_MARKET,
        user_url: str = POLYMARKET_WS_USER,
        stall_timeout_s: float = 90.0,
        auto_reconnect: bool = True,
        max_reconnect_attempts: int = 0,  # 0 = infinite
        proxy: str | None = None,
        on_book: Callable[[dict[str, Any]], Any] | None = None,
        on_price_change: Callable[[dict[str, Any]], Any] | None = None,
        on_last_trade: Callable[[dict[str, Any]], Any] | None = None,
        on_order: Callable[[dict[str, Any]], Any] | None = None,
        on_trade: Callable[[dict[str, Any]], Any] | None = None,
        on_stall: Callable[[StallTimeoutMeta], Any] | None = None,
        on_disconnect: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        config = WSClientConfig(url=market_url, exchange="polymarket")
        super().__init__(config, **kwargs)

        self._market_url = market_url
        self._user_url = user_url
        self._auto_reconnect = auto_reconnect
        self._max_reconnect_attempts = max_reconnect_attempts
        self._proxy = proxy

        self._ws_market: websockets.asyncio.client.ClientConnection | None = None
        self._ws_user: websockets.asyncio.client.ClientConnection | None = None
        self._recv_market_task: asyncio.Task[None] | None = None
        self._recv_user_task: asyncio.Task[None] | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._closing = False

        self._stall_watchdog = StallWatchdog(
            timeout_s=stall_timeout_s,
            on_timeout=on_stall or self._default_stall_handler,
            label="polymarket-ws-stall",
        )

        self.on_book = on_book
        self.on_price_change = on_price_change
        self.on_last_trade = on_last_trade
        self.on_order = on_order
        self.on_trade = on_trade
        self.on_disconnect_cb = on_disconnect

        self._user_authenticated = False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the market WebSocket connection with retry.

        The user socket is connected lazily when :meth:`subscribe_user`
        is called, since it requires API credentials.
        """
        self._closing = False
        await self._connect_market()

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Build kwargs for websockets.connect, including proxy if set."""
        kw: dict[str, Any] = {"open_timeout": 15, "close_timeout": 5}
        if self._proxy:
            kw["proxy"] = self._proxy
        return kw

    async def _connect_market(self) -> None:
        """Connect (or reconnect) the market WebSocket."""
        logger.info(
            "Connecting to Polymarket market WS: %s (proxy=%s)",
            self._market_url,
            self._proxy or "none",
        )
        self._ws_market = await websockets.asyncio.client.connect(
            self._market_url,
            **self._ws_connect_kwargs(),
        )

        await self._dispatch_connect()
        await self._stall_watchdog.start()
        self._stall_watchdog.arm()

        self._recv_market_task = asyncio.create_task(
            self._receive_loop(self._ws_market, "market"),
            name="polymarket-ws-market-recv",
        )

        # Start PING keepalive per Polymarket docs (every 50s)
        if self._ping_task is None or self._ping_task.done():
            self._ping_task = asyncio.create_task(self._ping_loop(), name="polymarket-ws-ping")

    async def _connect_user(self) -> None:
        """Open the user WebSocket connection (called by subscribe_user)."""
        if self._ws_user is not None:
            return
        logger.info("Connecting to Polymarket user WS: %s", self._user_url)
        self._ws_user = await websockets.asyncio.client.connect(
            self._user_url,
            **self._ws_connect_kwargs(),
        )
        self._recv_user_task = asyncio.create_task(
            self._receive_loop(self._ws_user, "user"),
            name="polymarket-ws-user-recv",
        )

    # ------------------------------------------------------------------
    # PING keepalive (Polymarket requires text "PING" every 50s)
    # ------------------------------------------------------------------

    async def _ping_loop(self) -> None:
        """Send ``"PING"`` text to all open sockets every 50 seconds."""
        try:
            while not self._closing:
                await asyncio.sleep(PING_INTERVAL_S)
                for ws, label in [
                    (self._ws_market, "market"),
                    (self._ws_user, "user"),
                ]:
                    if ws is not None:
                        try:
                            await ws.send("PING")
                        except Exception:
                            logger.debug("PING failed on %s socket", label)
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Auto-reconnect
    # ------------------------------------------------------------------

    async def _reconnect(self) -> None:
        """Attempt to reconnect the market WS with exponential backoff."""
        if self._closing or not self._auto_reconnect:
            return

        attempt = 0
        while not self._closing:
            attempt += 1
            if self._max_reconnect_attempts and attempt > self._max_reconnect_attempts:
                logger.error(
                    "Polymarket WS: exceeded max reconnect attempts (%d)",
                    self._max_reconnect_attempts,
                )
                break

            delay = min(1.0 * (2 ** min(attempt, 6)), 60.0)
            logger.info("Polymarket WS reconnect attempt %d in %.1fs", attempt, delay)
            await asyncio.sleep(delay)

            try:
                await self._connect_market()
                # Re-subscribe to all previously active market subscriptions
                market_tokens = [s.split(":", 1)[1] for s in self._subscriptions if s.startswith("market:")]
                if market_tokens:
                    await self.subscribe_market(market_tokens)
                logger.info("Polymarket WS reconnected after %d attempts", attempt)
                return
            except Exception as exc:
                logger.warning("Polymarket WS reconnect attempt %d failed: %s", attempt, exc)

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    async def subscribe(self, streams: list[str]) -> None:
        """Subscribe to market channels by asset/token IDs."""
        await self.subscribe_market(streams)

    async def subscribe_market(self, token_ids: list[str]) -> None:
        """Subscribe to public market data for specific tokens.

        Sends ``initial_dump: true`` to receive full orderbook snapshot on subscribe.
        """
        if not token_ids or self._ws_market is None:
            return

        self._subscriptions.update(f"market:{tid}" for tid in token_ids)

        # "market" channel gives price changes and last trade
        msg_market = {
            "assets_ids": token_ids,
            "type": "market",
        }
        await self._ws_market.send(json.dumps(msg_market))

        # "book" channel gives full orderbook updates (or deltas handled by client)
        msg_book = {
            "assets_ids": token_ids,
            "type": "book",
        }
        await self._ws_market.send(json.dumps(msg_book))

        logger.info("Polymarket market & book subscribe: %d tokens", len(token_ids))

    async def subscribe_user(
        self,
        *,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        markets: list[str] | None = None,
    ) -> None:
        """Subscribe to authenticated user channel for order/trade events."""
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
        """Unsubscribe from market token streams."""
        self._subscriptions -= set(streams)

        market_tokens = [s.split(":", 1)[1] for s in streams if s.startswith("market:")]
        if market_tokens and self._ws_market is not None:
            await self._ws_market.send(
                json.dumps(
                    {
                        "assets_ids": market_tokens,
                        "type": "unsubscribe_market",
                    }
                )
            )
            await self._ws_market.send(
                json.dumps(
                    {
                        "assets_ids": market_tokens,
                        "type": "unsubscribe_book",
                    }
                )
            )
            logger.info("Polymarket market unsubscribe: %d tokens", len(market_tokens))

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close all WebSocket connections."""
        self._closing = True
        self._stall_watchdog.stop()

        for task in (self._recv_market_task, self._recv_user_task, self._ping_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._recv_market_task = None
        self._recv_user_task = None
        self._ping_task = None

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

    @property
    def is_connected(self) -> bool:
        """Whether the market WebSocket is open."""
        return self._ws_market is not None

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
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    if raw == "PONG":
                        self._stall_watchdog.touch()
                        continue
                    parsed: Any = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    logger.debug("Non-JSON from Polymarket %s: %s", label, str(raw)[:200])
                    continue

                # Polymarket may send a single dict or a list of dicts
                items: list[dict[str, Any]] = parsed if isinstance(parsed, list) else [parsed]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    await self._route_message(item, label)
        except websockets.ConnectionClosed as exc:
            logger.info("Polymarket %s WS closed: %s", label, exc)
            if label == "user":
                self._user_authenticated = False
            await self._dispatch_disconnect(code=getattr(exc, "code", 1006), reason=str(exc))
            if label == "market":
                self._ws_market = None
                if self.on_disconnect_cb:
                    try:
                        result = self.on_disconnect_cb()
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass
                asyncio.ensure_future(self._reconnect())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Error in Polymarket %s receive loop: %s", label, exc)
            await self._dispatch_error(exc)
            if label == "market":
                self._ws_market = None
                asyncio.ensure_future(self._reconnect())

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
