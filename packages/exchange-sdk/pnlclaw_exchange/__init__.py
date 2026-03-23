"""pnlclaw_exchange -- Native exchange WebSocket and REST adapters."""

from pnlclaw_exchange.base.auth import (
    BaseAuthenticator,
    BinanceAuthenticator,
    ExchangeCredentials,
    OKXAuthenticator,
)
from pnlclaw_exchange.base.rate_limiter import SlidingWindowRateLimiter
from pnlclaw_exchange.base.reconciliation import ReconciliationManager
from pnlclaw_exchange.base.reconnect import ReconnectManager
from pnlclaw_exchange.base.rest_client import BaseRESTClient
from pnlclaw_exchange.base.stall_watchdog import StallTimeoutMeta, StallWatchdog
from pnlclaw_exchange.base.ws_client import BaseWSClient
from pnlclaw_exchange.exceptions import (
    AuthenticationError,
    ExchangeAPIError,
    InsufficientBalanceError,
    InvalidOrderError,
    OrderNotFoundError,
    OrderRejectedError,
    RateLimitExceededError,
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
from pnlclaw_exchange.exchanges.binance.rest_client import (
    BinanceOrderType,
    BinanceRESTClient,
    BinanceTimeInForce,
)
from pnlclaw_exchange.exchanges.binance.user_data_client import (
    BinanceUserDataClient,
    BinanceUserDataNormalizer,
)
from pnlclaw_exchange.exchanges.binance.ws_client import BinanceWSClient
from pnlclaw_exchange.exchanges.okx.normalizer import OKXNormalizer
from pnlclaw_exchange.exchanges.okx.private_client import (
    OKXPrivateNormalizer,
    OKXPrivateWSClient,
)
from pnlclaw_exchange.exchanges.okx.rest_client import (
    OKXOrderType,
    OKXRESTClient,
    OKXTradeMode,
)
from pnlclaw_exchange.exchanges.okx.ws_client import OKXWSClient
from pnlclaw_exchange.exchanges.polymarket.client import PolymarketClient
from pnlclaw_exchange.exchanges.polymarket.models import (
    AutoRedeemSummary,
    PolymarketMarket,
    PolymarketOrderBook,
    PolymarketPosition,
    PolymarketPositionStatus,
    PolymarketPrice,
    PolymarketToken,
    RedemptionResult,
)
from pnlclaw_exchange.exchanges.polymarket.redemption import (
    PolymarketRedemptionClient,
)
from pnlclaw_exchange.exchanges.polymarket.trading import (
    PolymarketCredentials,
    PolymarketOrderType,
    PolymarketSide,
    PolymarketTradingClient,
)
from pnlclaw_exchange.exchanges.polymarket.ws_client import (
    PolymarketEventType,
    PolymarketOrderEventType,
    PolymarketTradeStatus,
    PolymarketWSClient,
)
from pnlclaw_exchange.execution.live_engine import LiveExecutionEngine
from pnlclaw_exchange.normalizers.symbol import ExchangeSymbolRule, SymbolNormalizer
from pnlclaw_exchange.trading import (
    BalanceInfo,
    BinanceTradingAdapter,
    OKXTradingAdapter,
    OrderRequest,
    OrderResponse,
    PolymarketTradingAdapter,
    TradingClient,
)

__all__ = [
    # Base abstractions
    "BaseWSClient",
    "BaseRESTClient",
    "BaseAuthenticator",
    "ExchangeCredentials",
    "BinanceAuthenticator",
    "OKXAuthenticator",
    "ReconciliationManager",
    "ReconnectManager",
    "StallWatchdog",
    "StallTimeoutMeta",
    "SlidingWindowRateLimiter",
    # Unified trading interface
    "LiveExecutionEngine",
    "TradingClient",
    "OrderRequest",
    "OrderResponse",
    "BalanceInfo",
    "BinanceTradingAdapter",
    "OKXTradingAdapter",
    "PolymarketTradingAdapter",
    # Binance implementation
    "BinanceWSClient",
    "BinanceUserDataClient",
    "BinanceUserDataNormalizer",
    "BinanceNormalizer",
    "BinanceDepthDelta",
    "BinanceL2Manager",
    "BinanceRESTClient",
    "BinanceOrderType",
    "BinanceTimeInForce",
    # OKX implementation
    "OKXWSClient",
    "OKXNormalizer",
    "OKXPrivateWSClient",
    "OKXPrivateNormalizer",
    "OKXRESTClient",
    "OKXOrderType",
    "OKXTradeMode",
    # Polymarket implementation
    "PolymarketClient",
    "PolymarketTradingClient",
    "PolymarketCredentials",
    "PolymarketOrderType",
    "PolymarketSide",
    "PolymarketWSClient",
    "PolymarketEventType",
    "PolymarketOrderEventType",
    "PolymarketTradeStatus",
    "PolymarketMarket",
    "PolymarketOrderBook",
    "PolymarketPrice",
    "PolymarketToken",
    "PolymarketPosition",
    "PolymarketPositionStatus",
    "PolymarketRedemptionClient",
    "RedemptionResult",
    "AutoRedeemSummary",
    # Normalizers
    "SymbolNormalizer",
    "ExchangeSymbolRule",
    # Exceptions
    "WebSocketConnectionError",
    "WebSocketSubscriptionError",
    "StallTimeoutError",
    "SequenceGapError",
    "SnapshotRecoveryError",
    "ExchangeAPIError",
    "AuthenticationError",
    "RateLimitExceededError",
    "InsufficientBalanceError",
    "OrderNotFoundError",
    "OrderRejectedError",
    "InvalidOrderError",
]
