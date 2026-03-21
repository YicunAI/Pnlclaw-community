"""pnlclaw_exchange -- Native exchange WebSocket and REST adapters."""

from pnlclaw_exchange.base.rate_limiter import SlidingWindowRateLimiter
from pnlclaw_exchange.base.reconnect import ReconnectManager
from pnlclaw_exchange.base.stall_watchdog import StallTimeoutMeta, StallWatchdog
from pnlclaw_exchange.base.ws_client import BaseWSClient
from pnlclaw_exchange.exceptions import (
    SequenceGapError,
    SnapshotRecoveryError,
    StallTimeoutError,
    WebSocketConnectionError,
    WebSocketSubscriptionError,
)
from pnlclaw_exchange.exchanges.binance.l2_manager import BinanceL2Manager
from pnlclaw_exchange.exchanges.binance.normalizer import (
    BinanceDepthDelta,
    BinanceNormalizer,
)
from pnlclaw_exchange.exchanges.binance.ws_client import BinanceWSClient
from pnlclaw_exchange.normalizers.symbol import ExchangeSymbolRule, SymbolNormalizer

__all__ = [
    # Base abstractions
    "BaseWSClient",
    "ReconnectManager",
    "StallWatchdog",
    "StallTimeoutMeta",
    "SlidingWindowRateLimiter",
    # Binance implementation
    "BinanceWSClient",
    "BinanceNormalizer",
    "BinanceDepthDelta",
    "BinanceL2Manager",
    # Normalizers
    "SymbolNormalizer",
    "ExchangeSymbolRule",
    # Exceptions
    "WebSocketConnectionError",
    "WebSocketSubscriptionError",
    "StallTimeoutError",
    "SequenceGapError",
    "SnapshotRecoveryError",
]
