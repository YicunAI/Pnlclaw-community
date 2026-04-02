"""Binance L2 orderbook manager with gap detection and auto-recovery.

Implements Binance's diff depth stream protocol:

1. Open ``@depth@100ms`` stream.
2. GET ``/api/v3/depth`` REST snapshot.
3. Drop events where ``u <= lastUpdateId`` from the snapshot.
4. First event should have ``U <= lastUpdateId+1 AND u >= lastUpdateId+1``.
5. Subsequent events must have ``U == previous_u + 1`` (contiguous).
6. On any gap: discard local snapshot, REST-fetch a new one (< 1 s target).

Invariant: ``best_bid < best_ask`` must always hold.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from pnlclaw_exchange.base.rate_limiter import SlidingWindowRateLimiter
from pnlclaw_exchange.exceptions import SnapshotRecoveryError
from pnlclaw_exchange.exchanges.binance.normalizer import BinanceDepthDelta
from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer
from pnlclaw_types.market import OrderBookL2Snapshot, PriceLevel

logger = logging.getLogger(__name__)

BINANCE_REST_DEPTH_URL = "https://api.binance.com/api/v3/depth"
DEFAULT_DEPTH_LIMIT = 1000

Callback = Callable[..., Any]


_RECOVERY_COOLDOWN_S = 5.0


@dataclass
class _LocalOrderBook:
    """Internal per-symbol orderbook state."""

    symbol: str
    unified_symbol: str
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    last_update_id: int = 0
    initialized: bool = False  # True after first valid delta applied
    recovering: bool = False
    last_recovery_at: float = 0.0


class BinanceL2Manager:
    """Maintain local L2 orderbook state for Binance symbols.

    Contract:
        - Applies ``BinanceDepthDelta`` events to a local snapshot.
        - Detects sequence gaps via ``lastUpdateId`` continuity checks.
        - On gap: discards local data, fetches REST snapshot, resets state.
        - Validates ``best_bid < best_ask`` after every update.
        - Recovery target: < 1 s.
    """

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        symbol_normalizer: SymbolNormalizer | None = None,
        on_snapshot: Callback | None = None,
        rest_url: str = BINANCE_REST_DEPTH_URL,
        depth_limit: int = DEFAULT_DEPTH_LIMIT,
    ) -> None:
        self._http = http_client
        self._owns_http = http_client is None
        self._rate_limiter = rate_limiter
        self._symbols = symbol_normalizer or SymbolNormalizer()
        self._on_snapshot = on_snapshot
        self._rest_url = rest_url
        self._depth_limit = depth_limit

        self._books: dict[str, _LocalOrderBook] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def initialize(self, symbol: str) -> OrderBookL2Snapshot:
        """Initialize the L2 orderbook for a symbol via REST snapshot.

        Args:
            symbol: Binance symbol, e.g. ``"BTCUSDT"``.

        Returns:
            The initial ``OrderBookL2Snapshot``.
        """
        unified = self._symbols.to_unified("binance", symbol)
        book = _LocalOrderBook(symbol=symbol, unified_symbol=unified)
        self._books[symbol.upper()] = book

        await self._fetch_and_apply_snapshot(book)
        return self._build_snapshot(book)

    async def reinitialize_all(self) -> None:
        """Re-initialize all tracked symbols via fresh REST snapshots.

        Should be called after a WebSocket reconnect to discard stale
        local state that would otherwise cause false gap detections.
        """
        symbols = list(self._books.keys())
        if not symbols:
            return
        logger.info("Re-initializing L2 for %d symbols after reconnect", len(symbols))
        for key in symbols:
            book = self._books.get(key)
            if book is None:
                continue
            try:
                book.bids.clear()
                book.asks.clear()
                book.initialized = False
                book.recovering = False
                book.last_recovery_at = 0.0
                await self._fetch_and_apply_snapshot(book)
                logger.info("L2 re-initialized for %s (lastUpdateId=%d)", key, book.last_update_id)
            except Exception:
                logger.warning("L2 re-init failed for %s", key, exc_info=True)

    async def apply_delta(
        self, symbol: str, delta: BinanceDepthDelta
    ) -> bool:
        """Apply a depth delta to the local orderbook.

        Implements the Binance diff depth stream protocol (steps 3-5).
        Does NOT build a full snapshot on every delta; callers should use
        ``get_snapshot()`` when they need the sorted book.

        Args:
            symbol: Binance symbol, e.g. ``"BTCUSDT"``.
            delta: The normalized depth delta from the WebSocket stream.

        Returns:
            ``True`` if the delta was applied, ``False`` if it was dropped.
        """
        key = symbol.upper()
        book = self._books.get(key)

        if book is None:
            logger.warning("No local book for %s — call initialize() first", symbol)
            return False

        if book.recovering:
            return False

        # Step 3: Drop stale events.
        if delta.last_update_id <= book.last_update_id:
            return False

        # Step 4: First delta after snapshot.
        if not book.initialized:
            if (
                delta.first_update_id <= book.last_update_id + 1
                and delta.last_update_id >= book.last_update_id + 1
            ):
                book.initialized = True
            elif delta.last_update_id <= book.last_update_id:
                return False
            else:
                logger.info(
                    "Accepting first delta for %s with gap "
                    "(snapshot=%d, delta U=%d u=%d)",
                    symbol,
                    book.last_update_id,
                    delta.first_update_id,
                    delta.last_update_id,
                )
                book.initialized = True
        else:
            # Step 5: Contiguous check.
            if delta.previous_update_id is not None:
                if delta.previous_update_id != book.last_update_id:
                    pu_gap = delta.previous_update_id - book.last_update_id
                    logger.warning(
                        "Futures sequence break for %s (expected pu=%d, got pu=%d, diff=%d) — recovering",
                        symbol,
                        book.last_update_id,
                        delta.previous_update_id,
                        pu_gap,
                    )
                    await self._recover(book)
                    return False
            else:
                gap = delta.first_update_id - (book.last_update_id + 1)
                if gap > 0 and gap > 500:
                    logger.warning(
                        "Large sequence gap for %s (expected U=%d, got U=%d, gap=%d) — recovering",
                        symbol,
                        book.last_update_id + 1,
                        delta.first_update_id,
                        gap,
                    )
                    await self._recover(book)
                    return False
                elif gap > 0:
                    logger.debug(
                        "Small sequence gap for %s (gap=%d), accepting",
                        symbol,
                        gap,
                    )

        # Apply the delta.
        self._apply_levels(book.bids, delta.delta.bids)
        self._apply_levels(book.asks, delta.delta.asks)
        book.last_update_id = delta.last_update_id

        # Depth validation: best bid < best ask.
        if not self._validate_depth(book):
            logger.warning("Depth validation failed for %s (bid >= ask) — recovering", symbol)
            await self._recover(book)
            return False

        return True

    def get_snapshot(self, symbol: str) -> OrderBookL2Snapshot | None:
        """Return the current snapshot for a symbol, or None."""
        key = symbol.upper()
        book = self._books.get(key)
        if book is None:
            return None
        return self._build_snapshot(book)

    async def close(self) -> None:
        """Clean up resources."""
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------

    async def _recover(self, book: _LocalOrderBook) -> None:
        """Discard local data and fetch a fresh REST snapshot.

        Enforces a cooldown of ``_RECOVERY_COOLDOWN_S`` seconds between
        consecutive recoveries for the same symbol to avoid rate-limit
        exhaustion on high-frequency gap streams.
        """
        now = time.monotonic()
        if now - book.last_recovery_at < _RECOVERY_COOLDOWN_S:
            return

        book.recovering = True
        book.initialized = False
        book.bids.clear()
        book.asks.clear()
        book.last_recovery_at = now

        logger.info("Recovering L2 orderbook for %s via REST", book.symbol)
        start = time.monotonic()

        try:
            await self._fetch_and_apply_snapshot(book)
            elapsed = time.monotonic() - start
            logger.info("L2 recovery for %s completed in %.3fs", book.symbol, elapsed)
        except Exception as exc:
            logger.error("L2 recovery failed for %s: %s", book.symbol, exc)
            raise SnapshotRecoveryError(
                f"Failed to recover L2 orderbook for {book.symbol}",
                symbol=book.symbol,
                details={"error": str(exc)},
            ) from exc
        finally:
            book.recovering = False

    async def _fetch_and_apply_snapshot(self, book: _LocalOrderBook) -> None:
        """Fetch a REST depth snapshot and apply it to the local book."""
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()

        client = self._http or httpx.AsyncClient()
        try:
            resp = await client.get(
                self._rest_url,
                params={"symbol": book.symbol.upper(), "limit": self._depth_limit},
            )
            resp.raise_for_status()
            data = resp.json()
        finally:
            if self._http is None:
                await client.aclose()

        # Apply snapshot.
        book.bids.clear()
        book.asks.clear()
        for entry in data.get("bids", []):
            price = float(entry[0])
            qty = float(entry[1])
            if qty > 0:
                book.bids[price] = qty
        for entry in data.get("asks", []):
            price = float(entry[0])
            qty = float(entry[1])
            if qty > 0:
                book.asks[price] = qty

        book.last_update_id = int(data["lastUpdateId"])
        book.initialized = False  # Will be set on first valid delta.

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_levels(side: dict[float, float], updates: list[PriceLevel]) -> None:
        """Apply delta updates to one side of the book.

        quantity == 0 means remove the price level.
        """
        for level in updates:
            if level.quantity == 0:
                side.pop(level.price, None)
            else:
                side[level.price] = level.quantity

    @staticmethod
    def _validate_depth(book: _LocalOrderBook) -> bool:
        """Check that best bid < best ask."""
        if not book.bids or not book.asks:
            return True  # Empty side is valid.
        best_bid = max(book.bids.keys())
        best_ask = min(book.asks.keys())
        return best_bid < best_ask

    def _build_snapshot(self, book: _LocalOrderBook) -> OrderBookL2Snapshot:
        """Build an OrderBookL2Snapshot from the local book state."""
        bids = [PriceLevel(price=p, quantity=q) for p, q in sorted(book.bids.items(), reverse=True)]
        asks = [PriceLevel(price=p, quantity=q) for p, q in sorted(book.asks.items())]
        return OrderBookL2Snapshot(
            exchange="binance",
            symbol=book.unified_symbol,
            timestamp=int(time.time() * 1000),
            sequence_id=book.last_update_id,
            bids=bids,
            asks=asks,
        )
