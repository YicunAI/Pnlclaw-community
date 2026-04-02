"""Binance WebSocket message normalizer.

Converts Binance-specific JSON messages into unified PnLClaw event models
defined in ``pnlclaw_types.market``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer
from pnlclaw_types.derivatives import FundingRateEvent, LiquidationEvent
from pnlclaw_types.market import (
    KlineEvent,
    OrderBookL2Delta,
    PriceLevel,
    TickerEvent,
    TradeEvent,
)

logger = logging.getLogger(__name__)

EXCHANGE = "binance"


@dataclass
class BinanceDepthDelta:
    """Binance-specific depth delta wrapping the unified model.

    Binance's diff depth stream provides both ``U`` (first update ID) and
    ``u`` (last update ID) for gap detection, while the unified
    :class:`OrderBookL2Delta` has only a single ``sequence_id``.

    Futures streams additionally include ``pu`` (previous final update ID)
    which enables linked-list-style continuity checking instead of the
    strict ``U == prev_u + 1`` rule used by spot.
    """

    delta: OrderBookL2Delta
    first_update_id: int  # Binance ``U`` field
    last_update_id: int  # Binance ``u`` field
    previous_update_id: int | None = None  # Binance ``pu`` field (futures only)


class BinanceNormalizer:
    """Convert Binance WebSocket JSON → unified PnLClaw event models.

    Contract:
        - Handles Binance's single-letter field names (``e``, ``s``, ``E``, …).
        - Symbol normalization via :class:`SymbolNormalizer`.
        - Returns ``None`` for unrecognized event types (graceful degradation).
    """

    def __init__(self, symbol_normalizer: SymbolNormalizer) -> None:
        self._symbols = symbol_normalizer

    def normalize(
        self, data: dict[str, Any]
    ) -> TickerEvent | TradeEvent | KlineEvent | BinanceDepthDelta | LiquidationEvent | FundingRateEvent | None:
        """Dispatch normalization based on Binance's ``e`` (event type) field.

        Returns:
            A unified event model or ``None`` if the event type is unrecognized.
        """
        event_type = data.get("e")

        if event_type == "24hrTicker":
            return self._normalize_ticker(data)
        if event_type == "trade":
            return self._normalize_trade(data)
        if event_type == "aggTrade":
            return self._normalize_agg_trade(data)
        if event_type == "kline":
            return self._normalize_kline(data)
        if event_type == "depthUpdate":
            return self._normalize_depth(data)
        if event_type == "forceOrder":
            return self._normalize_liquidation(data)
        if event_type == "markPriceUpdate":
            return self._normalize_funding_rate(data)

        logger.debug("Unrecognized Binance event type: %s", event_type)
        return None

    # ------------------------------------------------------------------
    # Private normalizers
    # ------------------------------------------------------------------

    def _normalize_ticker(self, data: dict[str, Any]) -> TickerEvent:
        return TickerEvent(
            exchange=EXCHANGE,
            symbol=self._symbols.to_unified(EXCHANGE, data["s"]),
            timestamp=int(data["E"]),
            last_price=float(data["c"]),
            bid=float(data.get("b", 0) or 0),
            ask=float(data.get("a", 0) or 0),
            volume_24h=float(data["v"]),
            quote_volume_24h=float(data["q"]),
            high_24h=float(data["h"]),
            low_24h=float(data["l"]),
            change_24h_pct=float(data["P"]),
        )

    def _normalize_trade(self, data: dict[str, Any]) -> TradeEvent:
        # Binance ``m`` = buyer is market maker.
        # If True, the trade was initiated by a seller → side = "sell".
        side = "sell" if data["m"] else "buy"
        return TradeEvent(
            exchange=EXCHANGE,
            symbol=self._symbols.to_unified(EXCHANGE, data["s"]),
            timestamp=int(data["E"]),
            trade_id=str(data["t"]),
            price=float(data["p"]),
            quantity=float(data["q"]),
            side=side,
        )

    def _normalize_kline(self, data: dict[str, Any]) -> KlineEvent:
        k = data["k"]
        return KlineEvent(
            exchange=EXCHANGE,
            symbol=self._symbols.to_unified(EXCHANGE, k["s"]),
            timestamp=int(k["t"]),
            interval=k["i"],
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            closed=bool(k["x"]),
        )

    def _normalize_agg_trade(self, data: dict[str, Any]) -> TradeEvent:
        """Normalize Binance aggregated trade (``aggTrade``) event.

        Field ``m`` = buyer is market maker → if True the taker was selling.
        Uses ``a`` (aggregate trade ID) instead of ``t`` (individual trade ID).
        """
        side = "sell" if data["m"] else "buy"
        return TradeEvent(
            exchange=EXCHANGE,
            symbol=self._symbols.to_unified(EXCHANGE, data["s"]),
            timestamp=int(data["E"]),
            trade_id=str(data["a"]),
            price=float(data["p"]),
            quantity=float(data["q"]),
            side=side,
        )

    def _normalize_liquidation(self, data: dict[str, Any]) -> LiquidationEvent:
        """Normalize Binance forced-liquidation (``forceOrder``) event.

        ``o.S`` = "SELL" means a long position was liquidated.
        ``o.S`` = "BUY" means a short position was liquidated.
        """
        o = data["o"]
        side: str = "long" if o["S"] == "SELL" else "short"
        qty = float(o["q"])
        price = float(o["p"])
        avg_price = float(o.get("ap", 0) or 0)
        notional = qty * (avg_price if avg_price > 0 else price)
        return LiquidationEvent(
            exchange=EXCHANGE,
            symbol=self._symbols.to_unified(EXCHANGE, o["s"]),
            side=side,
            quantity=qty,
            price=price,
            avg_price=avg_price,
            notional_usd=notional,
            status=o.get("X", "FILLED"),
            timestamp=int(data["E"]),
        )

    def _normalize_funding_rate(self, data: dict[str, Any]) -> FundingRateEvent:
        """Normalize Binance mark price update containing funding rate."""
        return FundingRateEvent(
            exchange=EXCHANGE,
            symbol=self._symbols.to_unified(EXCHANGE, data["s"]),
            funding_rate=float(data.get("r", 0) or 0),
            mark_price=float(data.get("p", 0) or 0),
            index_price=float(data.get("i", 0) or 0),
            next_funding_time=int(data.get("T", 0) or 0),
            timestamp=int(data["E"]),
        )

    def _normalize_depth(self, data: dict[str, Any]) -> BinanceDepthDelta:
        symbol = self._symbols.to_unified(EXCHANGE, data["s"])
        timestamp = int(data["E"])
        first_update_id = int(data["U"])
        last_update_id = int(data["u"])
        previous_update_id = int(data["pu"]) if "pu" in data else None

        bids = [PriceLevel(price=float(entry[0]), quantity=float(entry[1])) for entry in data.get("b", [])]
        asks = [PriceLevel(price=float(entry[0]), quantity=float(entry[1])) for entry in data.get("a", [])]

        delta = OrderBookL2Delta(
            exchange=EXCHANGE,
            symbol=symbol,
            timestamp=timestamp,
            sequence_id=last_update_id,
            bids=bids,
            asks=asks,
        )

        return BinanceDepthDelta(
            delta=delta,
            first_update_id=first_update_id,
            last_update_id=last_update_id,
            previous_update_id=previous_update_id,
        )
