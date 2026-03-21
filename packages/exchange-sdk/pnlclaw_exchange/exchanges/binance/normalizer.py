"""Binance WebSocket message normalizer.

Converts Binance-specific JSON messages into unified PnLClaw event models
defined in ``pnlclaw_types.market``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pnlclaw_types.market import (
    KlineEvent,
    OrderBookL2Delta,
    PriceLevel,
    TickerEvent,
    TradeEvent,
)

from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer

logger = logging.getLogger(__name__)

EXCHANGE = "binance"


@dataclass
class BinanceDepthDelta:
    """Binance-specific depth delta wrapping the unified model.

    Binance's diff depth stream provides both ``U`` (first update ID) and
    ``u`` (last update ID) for gap detection, while the unified
    :class:`OrderBookL2Delta` has only a single ``sequence_id``.
    """

    delta: OrderBookL2Delta
    first_update_id: int  # Binance ``U`` field
    last_update_id: int  # Binance ``u`` field


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
    ) -> TickerEvent | TradeEvent | KlineEvent | BinanceDepthDelta | None:
        """Dispatch normalization based on Binance's ``e`` (event type) field.

        Returns:
            A unified event model or ``None`` if the event type is unrecognized.
        """
        event_type = data.get("e")

        if event_type == "24hrTicker":
            return self._normalize_ticker(data)
        if event_type == "trade":
            return self._normalize_trade(data)
        if event_type == "kline":
            return self._normalize_kline(data)
        if event_type == "depthUpdate":
            return self._normalize_depth(data)

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
            bid=float(data["b"]),
            ask=float(data["a"]),
            volume_24h=float(data["v"]),
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
            timestamp=int(data["E"]),
            interval=k["i"],
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            closed=bool(k["x"]),
        )

    def _normalize_depth(self, data: dict[str, Any]) -> BinanceDepthDelta:
        symbol = self._symbols.to_unified(EXCHANGE, data["s"])
        timestamp = int(data["E"])
        first_update_id = int(data["U"])
        last_update_id = int(data["u"])

        bids = [
            PriceLevel(price=float(entry[0]), quantity=float(entry[1]))
            for entry in data.get("b", [])
        ]
        asks = [
            PriceLevel(price=float(entry[0]), quantity=float(entry[1]))
            for entry in data.get("a", [])
        ]

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
        )
