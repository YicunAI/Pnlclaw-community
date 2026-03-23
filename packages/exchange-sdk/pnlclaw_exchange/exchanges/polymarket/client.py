"""Polymarket CLOB REST client for public market data.

No authentication required for:
- Listing markets and events
- Orderbook data
- Midpoint / market prices

Docs: https://docs.polymarket.com/developers/CLOB/introduction

Base URL: https://clob.polymarket.com
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from pnlclaw_exchange.exchanges.polymarket.models import (
    PolymarketMarket,
    PolymarketOrderBook,
    PolymarketPrice,
    PolymarketToken,
)

logger = logging.getLogger(__name__)

DEFAULT_CLOB_URL = "https://clob.polymarket.com"
DEFAULT_GAMMA_URL = "https://gamma-api.polymarket.com"


class PolymarketClient:
    """Public REST client for Polymarket CLOB and Gamma APIs.

    The CLOB API handles orderbook and trading data.
    The Gamma API provides enriched market/event metadata.
    No API key is required for read-only public endpoints.
    """

    def __init__(
        self,
        *,
        clob_url: str = DEFAULT_CLOB_URL,
        gamma_url: str = DEFAULT_GAMMA_URL,
        timeout: float = 15.0,
    ) -> None:
        self._clob_url = clob_url.rstrip("/")
        self._gamma_url = gamma_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Markets
    # ------------------------------------------------------------------

    async def list_markets(
        self, *, limit: int = 20, next_cursor: str = ""
    ) -> list[PolymarketMarket]:
        """Fetch active prediction markets from the CLOB API.

        Returns a list of markets with their tokens and metadata.
        """
        params: dict[str, Any] = {"limit": limit, "active": "true"}
        if next_cursor:
            params["next_cursor"] = next_cursor

        resp = await self._http.get(f"{self._clob_url}/markets", params=params)
        resp.raise_for_status()
        raw = resp.json()

        markets_data = raw if isinstance(raw, list) else raw.get("data", [])
        result: list[PolymarketMarket] = []
        for m in markets_data:
            tokens = [
                PolymarketToken(
                    token_id=t["token_id"],
                    outcome=t.get("outcome", ""),
                    price=float(t.get("price", 0) or 0),
                    winner=bool(t.get("winner", False)),
                )
                for t in m.get("tokens", [])
            ]
            result.append(PolymarketMarket(
                condition_id=m.get("condition_id", ""),
                question_id=m.get("question_id", ""),
                question=m.get("question", ""),
                description=m.get("description", ""),
                market_slug=m.get("market_slug", ""),
                end_date_iso=m.get("end_date_iso", ""),
                active=m.get("active", True),
                closed=m.get("closed", False),
                tokens=tokens,
                volume=float(m.get("volume", 0) or 0),
                volume_24h=float(m.get("volume_num_24hr", 0) or 0),
                liquidity=float(m.get("liquidity", 0) or 0),
            ))
        return result

    # ------------------------------------------------------------------
    # Orderbook
    # ------------------------------------------------------------------

    async def get_orderbook(self, token_id: str) -> PolymarketOrderBook:
        """Fetch the order book for a specific token.

        Args:
            token_id: The asset/token ID (long hex string).

        Returns:
            PolymarketOrderBook with bids, asks, and metadata.
        """
        resp = await self._http.get(
            f"{self._clob_url}/book", params={"token_id": token_id}
        )
        resp.raise_for_status()
        data = resp.json()
        return PolymarketOrderBook(
            market=data.get("market", ""),
            asset_id=data.get("asset_id", token_id),
            timestamp=data.get("timestamp", ""),
            bids=data.get("bids", []),
            asks=data.get("asks", []),
            last_trade_price=data.get("last_trade_price", ""),
            tick_size=data.get("tick_size", "0.01"),
            min_order_size=data.get("min_order_size", "1"),
        )

    # ------------------------------------------------------------------
    # Prices
    # ------------------------------------------------------------------

    async def get_midpoint(self, token_id: str) -> float:
        """Get the midpoint price for a token.

        The midpoint is (best_bid + best_ask) / 2.
        """
        resp = await self._http.get(
            f"{self._clob_url}/midpoint", params={"token_id": token_id}
        )
        resp.raise_for_status()
        data = resp.json()
        return float(data.get("mid", 0))

    async def get_price(self, token_id: str, side: str = "BUY") -> float:
        """Get the best market price for a token on the given side.

        Args:
            token_id: Token ID.
            side: ``"BUY"`` or ``"SELL"``.
        """
        resp = await self._http.get(
            f"{self._clob_url}/price",
            params={"token_id": token_id, "side": side},
        )
        resp.raise_for_status()
        data = resp.json()
        return float(data.get("price", 0))

    async def get_last_trade_price(self, token_id: str) -> PolymarketPrice:
        """Get the last trade price for a token."""
        resp = await self._http.get(
            f"{self._clob_url}/last-trade-price",
            params={"token_id": token_id},
        )
        resp.raise_for_status()
        data = resp.json()
        return PolymarketPrice(
            token_id=token_id,
            price=float(data.get("price", 0)),
            side=data.get("side", ""),
        )

    # ------------------------------------------------------------------
    # Events (via Gamma API for richer metadata)
    # ------------------------------------------------------------------

    async def list_events(
        self, *, limit: int = 10, active: bool = True
    ) -> list[dict[str, Any]]:
        """List prediction events from the Gamma API.

        Events group related markets together (e.g. "2024 US Election"
        may have multiple sub-markets).
        """
        params: dict[str, Any] = {"limit": limit, "active": str(active).lower()}
        resp = await self._http.get(f"{self._gamma_url}/events", params=params)
        resp.raise_for_status()
        result: list[dict[str, Any]] = resp.json()
        return result

    # ------------------------------------------------------------------
    # Server time (for clock sync)
    # ------------------------------------------------------------------

    async def get_server_time(self) -> int:
        """Get server Unix timestamp."""
        resp = await self._http.get(f"{self._clob_url}/time")
        resp.raise_for_status()
        return int(resp.text)
