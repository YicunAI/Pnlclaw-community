"""Bulk funding rate fetcher for all perpetual futures across exchanges.

Fetches ALL funding rates from:
- Binance USDT-M Futures: GET /fapi/v1/premiumIndex (single call, all symbols)
- OKX Perpetual Swaps: GET /api/v5/public/funding-rate per instrument
  (batched concurrently with rate limiting)

Results are cached and refreshed on configurable intervals.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BINANCE_FAPI_URL = "https://fapi.binance.com"
OKX_API_URL = "https://www.okx.com"

CACHE_TTL_MS = 30_000
OKX_CONCURRENCY = 10


@dataclass
class FundingRateItem:
    exchange: str
    symbol: str
    funding_rate: float
    mark_price: float
    index_price: float
    next_funding_time: int
    timestamp: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "funding_rate": self.funding_rate,
            "mark_price": self.mark_price,
            "index_price": self.index_price,
            "next_funding_time": self.next_funding_time,
            "timestamp": self.timestamp,
        }


class FundingRateFetcher:
    """Asynchronously fetches and caches all-exchange funding rates."""

    def __init__(self, *, proxy_url: str | None = None) -> None:
        self._proxy_url = proxy_url
        self._cache: list[FundingRateItem] = []
        self._cache_ts: int = 0
        self._lock = asyncio.Lock()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            transport = None
            if self._proxy_url:
                transport = httpx.AsyncHTTPTransport(proxy=self._proxy_url)
            self._client = httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(15.0, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    async def get_all(self, *, force: bool = False) -> list[FundingRateItem]:
        now_ms = int(time.time() * 1000)
        if not force and self._cache and (now_ms - self._cache_ts) < CACHE_TTL_MS:
            return self._cache

        async with self._lock:
            if not force and self._cache and (int(time.time() * 1000) - self._cache_ts) < CACHE_TTL_MS:
                return self._cache

            binance_task = asyncio.create_task(self._fetch_binance())
            okx_task = asyncio.create_task(self._fetch_okx())

            binance_items, okx_items = await asyncio.gather(
                binance_task,
                okx_task,
                return_exceptions=True,
            )

            items: list[FundingRateItem] = []
            if isinstance(binance_items, list):
                items.extend(binance_items)
            else:
                logger.warning("Binance funding rate fetch failed: %s", binance_items)

            if isinstance(okx_items, list):
                items.extend(okx_items)
            else:
                logger.warning("OKX funding rate fetch failed: %s", okx_items)

            self._cache = items
            self._cache_ts = int(time.time() * 1000)
            return items

    async def _fetch_binance(self) -> list[FundingRateItem]:
        client = await self._get_client()
        resp = await client.get(f"{BINANCE_FAPI_URL}/fapi/v1/premiumIndex")
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()

        items: list[FundingRateItem] = []
        now_ms = int(time.time() * 1000)
        for row in data:
            raw_symbol: str = row.get("symbol", "")
            if not raw_symbol.endswith("USDT"):
                continue
            base = raw_symbol.replace("USDT", "")
            symbol = f"{base}/USDT"

            rate_str = row.get("lastFundingRate", "0")
            mark_str = row.get("markPrice", "0")
            index_str = row.get("indexPrice", "0")
            next_ts = int(row.get("nextFundingTime", 0))

            try:
                items.append(
                    FundingRateItem(
                        exchange="binance",
                        symbol=symbol,
                        funding_rate=float(rate_str),
                        mark_price=float(mark_str),
                        index_price=float(index_str),
                        next_funding_time=next_ts,
                        timestamp=now_ms,
                    )
                )
            except (ValueError, TypeError):
                continue

        logger.info("Binance: fetched %d funding rates", len(items))
        return items

    async def _fetch_okx(self) -> list[FundingRateItem]:
        client = await self._get_client()

        inst_resp = await client.get(
            f"{OKX_API_URL}/api/v5/public/instruments",
            params={"instType": "SWAP"},
        )
        inst_resp.raise_for_status()
        inst_data = inst_resp.json().get("data", [])

        usdt_instruments = [inst["instId"] for inst in inst_data if inst.get("instId", "").endswith("-USDT-SWAP")]

        if not usdt_instruments:
            return []

        sem = asyncio.Semaphore(OKX_CONCURRENCY)
        items: list[FundingRateItem] = []
        now_ms = int(time.time() * 1000)

        async def _fetch_one(inst_id: str) -> FundingRateItem | None:
            async with sem:
                try:
                    resp = await client.get(
                        f"{OKX_API_URL}/api/v5/public/funding-rate",
                        params={"instId": inst_id},
                    )
                    if resp.status_code != 200:
                        return None
                    rows = resp.json().get("data", [])
                    if not rows:
                        return None
                    row = rows[0]

                    parts = inst_id.split("-")
                    symbol = f"{parts[0]}/{parts[1]}" if len(parts) >= 2 else inst_id

                    return FundingRateItem(
                        exchange="okx",
                        symbol=symbol,
                        funding_rate=float(row.get("fundingRate", "0")),
                        mark_price=0.0,
                        index_price=0.0,
                        next_funding_time=int(row.get("nextFundingTime", "0")),
                        timestamp=now_ms,
                    )
                except Exception:
                    return None

        # Also fetch mark prices in bulk for OKX
        mark_prices: dict[str, float] = {}
        try:
            mp_resp = await client.get(
                f"{OKX_API_URL}/api/v5/public/mark-price",
                params={"instType": "SWAP"},
            )
            if mp_resp.status_code == 200:
                for mp in mp_resp.json().get("data", []):
                    mark_prices[mp.get("instId", "")] = float(mp.get("markPx", "0"))
        except Exception:
            pass

        tasks = [_fetch_one(inst_id) for inst_id in usdt_instruments]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, FundingRateItem):
                inst_id = usdt_instruments[i]
                result.mark_price = mark_prices.get(inst_id, 0.0)
                items.append(result)

        logger.info("OKX: fetched %d funding rates", len(items))
        return items

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
