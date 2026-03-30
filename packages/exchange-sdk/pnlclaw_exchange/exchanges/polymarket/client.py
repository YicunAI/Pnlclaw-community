"""Polymarket CLOB REST client for public market data.

No authentication required for:
- Listing markets and events
- Orderbook data
- Midpoint / market prices

Docs: https://docs.polymarket.com/developers/CLOB/introduction

Base URL: https://clob.polymarket.com
"""

from __future__ import annotations

import asyncio
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


def detect_local_proxy() -> str | None:
    """Detect the system proxy (env vars or Windows registry).

    Returns a URL like ``http://127.0.0.1:1081`` or ``None``.
    Shared between HTTP and WebSocket clients.
    """
    import os, sys

    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = os.environ.get(var, "").strip()
        if val:
            return val

    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            )
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            if enabled:
                server, _ = winreg.QueryValueEx(key, "ProxyServer")
                server = server.strip()
                if server and "://" not in server:
                    server = f"http://{server}"
                if server:
                    return server
        except Exception:
            pass

    return None
DEFAULT_GAMMA_URL = "https://gamma-api.polymarket.com"

_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 0.5


class PolymarketClient:
    """Public REST client for Polymarket CLOB and Gamma APIs.

    The CLOB API handles orderbook and trading data.
    The Gamma API provides enriched market/event metadata.
    No API key is required for read-only public endpoints.

    All HTTP requests are retried up to 3 times with exponential backoff.
    """

    def __init__(
        self,
        *,
        clob_url: str = DEFAULT_CLOB_URL,
        gamma_url: str = DEFAULT_GAMMA_URL,
        timeout: httpx.Timeout | float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._clob_url = clob_url.rstrip("/")
        self._gamma_url = gamma_url.rstrip("/")
        if isinstance(timeout, (int, float)):
            timeout = httpx.Timeout(connect=5.0, read=timeout, write=5.0, pool=5.0)
        self._timeout = timeout
        # Auto-detect local proxy from Windows registry.
        # httpx trust_env often misreads Windows ProxyServer registry (missing
        # scheme), so we detect it explicitly and set proxy= directly.
        proxy_url = self._detect_local_proxy()
        if proxy_url:
            logger.info("Polymarket HTTP: using proxy %s", proxy_url)

        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"Accept": "application/json"},
            follow_redirects=True,
            proxy=proxy_url,
            trust_env=False,
        )
        self._http_direct: httpx.AsyncClient | None = None

    @staticmethod
    def _detect_local_proxy() -> str | None:
        return detect_local_proxy()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
        if self._http_direct is not None:
            await self._http_direct.aclose()

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    def _get_direct_client(self) -> httpx.AsyncClient:
        """Lazy-init a direct (no-proxy) HTTP client as fallback."""
        if self._http_direct is None:
            self._http_direct = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"Accept": "application/json"},
                follow_redirects=True,
                trust_env=False,
            )
        return self._http_direct

    async def _try_get(
        self, client: httpx.AsyncClient, url: str, params: dict[str, Any] | None
    ) -> httpx.Response:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp

    async def _get_with_retry(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        max_retries: int = _MAX_RETRIES,
    ) -> httpx.Response:
        """GET with exponential backoff retry on transient errors.

        Strategy: try system-proxy client first; on ConnectTimeout/ConnectError
        fall back to direct client (no proxy). This handles environments where
        a local proxy (Clash/V2Ray) may or may not be running.
        """
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            for client, label in [
                (self._http, "proxy"),
                (self._get_direct_client(), "direct"),
            ]:
                try:
                    return await self._try_get(client, url, params)
                except (httpx.ConnectTimeout, httpx.ConnectError) as exc:
                    last_exc = exc
                    logger.debug(
                        "Polymarket %s %s failed (%s): %s",
                        label, url.split("/")[-1], type(exc).__name__, exc,
                    )
                    continue
                except httpx.ReadTimeout as exc:
                    last_exc = exc
                    break  # server reachable but slow, skip to retry
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in (429, 502, 503, 504):
                        last_exc = exc
                        break  # server error, skip to retry
                    raise

            if attempt < max_retries - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Polymarket API retry %d/%d for %s: %s (delay %.1fs)",
                    attempt + 1, max_retries, url.split("/")[-1],
                    type(last_exc).__name__ if last_exc else "unknown", delay,
                )
                await asyncio.sleep(delay)

        raise last_exc or httpx.ConnectError("All retries exhausted")

    # ------------------------------------------------------------------
    # Markets
    # ------------------------------------------------------------------

    async def list_markets(
        self, *, limit: int = 20, next_cursor: str = ""
    ) -> list[PolymarketMarket]:
        """Fetch active prediction markets from the CLOB API."""
        params: dict[str, Any] = {"limit": limit, "active": "true"}
        if next_cursor:
            params["next_cursor"] = next_cursor

        resp = await self._get_with_retry(f"{self._clob_url}/markets", params)
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
        """Fetch the order book for a specific token."""
        resp = await self._get_with_retry(
            f"{self._clob_url}/book", {"token_id": token_id}
        )
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
        """Get the midpoint price for a token."""
        resp = await self._get_with_retry(
            f"{self._clob_url}/midpoint", {"token_id": token_id}
        )
        data = resp.json()
        return float(data.get("mid", 0))

    async def get_price(self, token_id: str, side: str = "BUY") -> float:
        """Get the best market price for a token on the given side."""
        resp = await self._get_with_retry(
            f"{self._clob_url}/price", {"token_id": token_id, "side": side}
        )
        data = resp.json()
        return float(data.get("price", 0))

    async def get_last_trade_price(self, token_id: str) -> PolymarketPrice:
        """Get the last trade price for a token."""
        resp = await self._get_with_retry(
            f"{self._clob_url}/last-trade-price", {"token_id": token_id}
        )
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
        self,
        *,
        limit: int = 10,
        active: bool = True,
        closed: bool = False,
        order: str = "volume24hr",
        ascending: bool = False,
        end_date_min: str = "",
        end_date_max: str = "",
        start_date_min: str = "",
    ) -> list[dict[str, Any]]:
        """List prediction events from the Gamma API."""
        params: dict[str, Any] = {
            "limit": limit,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": order,
            "ascending": str(ascending).lower(),
        }
        if end_date_min:
            params["end_date_min"] = end_date_min
        if end_date_max:
            params["end_date_max"] = end_date_max
        if start_date_min:
            params["start_date_min"] = start_date_min
        resp = await self._get_with_retry(f"{self._gamma_url}/events", params)
        result: list[dict[str, Any]] = resp.json()
        return result

    async def get_event(self, event_id: str) -> dict[str, Any]:
        """Fetch a single event by ID from the Gamma API."""
        resp = await self._get_with_retry(f"{self._gamma_url}/events/{event_id}")
        result: dict[str, Any] = resp.json()
        return result

    async def get_event_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Fetch a single event by slug. Returns None if not found."""
        try:
            resp = await self._get_with_retry(
                f"{self._gamma_url}/events/slug/{slug}"
            )
            data = resp.json()
            if isinstance(data, dict) and data.get("id"):
                return data
            return None
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ConnectTimeout):
            return None

    async def search_markets_gamma(
        self,
        *,
        query: str = "",
        limit: int = 20,
        active: bool = True,
        closed: bool = False,
        order: str = "volume24hr",
        ascending: bool = False,
    ) -> list[dict[str, Any]]:
        """Search markets via the Gamma API with a text query."""
        params: dict[str, Any] = {
            "limit": limit,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": order,
            "ascending": str(ascending).lower(),
        }
        if query:
            params["_q"] = query
        resp = await self._get_with_retry(f"{self._gamma_url}/markets", params)
        result: list[dict[str, Any]] = resp.json()
        return result

    # ------------------------------------------------------------------
    # Server time (for clock sync)
    # ------------------------------------------------------------------

    async def get_server_time(self) -> int:
        """Get server Unix timestamp."""
        resp = await self._get_with_retry(f"{self._clob_url}/time")
        return int(resp.text)
