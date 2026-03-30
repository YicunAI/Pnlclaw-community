"""ExchangeSource protocol — pluggable exchange adapter for MarketDataService.

Each source wraps one (exchange, market_type) combination and manages its
own WS client, L2 state, reconnect loop, and per-symbol cache.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from pnlclaw_types.market import (
    KlineEvent,
    MarketType,
    OrderBookL2Snapshot,
    TickerEvent,
)


class ExchangeSourceConfig(BaseModel):
    """Identity of an exchange data source."""

    exchange: str = Field(..., description="Exchange id, e.g. 'binance'")
    market_type: MarketType = Field(..., description="Market type: 'spot' or 'futures'")


@runtime_checkable
class ExchangeSource(Protocol):
    """Contract every exchange source adapter must satisfy."""

    @property
    def config(self) -> ExchangeSourceConfig: ...

    @property
    def is_running(self) -> bool: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def subscribe(
        self,
        symbol: str,
        *,
        ticker: bool = True,
        kline: bool = True,
        depth: bool = True,
    ) -> None: ...

    async def unsubscribe(self, symbol: str) -> None: ...

    def get_ticker(self, symbol: str) -> TickerEvent | None: ...

    def get_kline(self, symbol: str) -> KlineEvent | None: ...

    def get_klines(self, symbol: str, limit: int = 100) -> list[KlineEvent]: ...

    def get_orderbook(self, symbol: str) -> OrderBookL2Snapshot | None: ...

    def get_symbols(self) -> list[str]: ...

    def on_ticker(self, callback: Callable[[TickerEvent], Any]) -> None: ...

    def on_kline(self, callback: Callable[[KlineEvent], Any]) -> None: ...

    def on_orderbook(self, callback: Callable[[OrderBookL2Snapshot], Any]) -> None: ...
