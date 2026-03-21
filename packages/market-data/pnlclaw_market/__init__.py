"""pnlclaw_market -- Market stream normalization, cache, event bus.

Public API
----------
- ``MarketDataService`` — main service managing subscriptions and data access.
- ``EventBus`` — type-safe internal event bus.
- ``MarketDataCache``, ``TTLLRUCache`` — TTL + LRU caching.
- ``StreamManager``, ``StreamType`` — WS stream lifecycle management.
- ``SnapshotStore`` — L2 orderbook snapshot storage.
- ``MarketStateEngine`` — market state classification engine.
"""

from pnlclaw_market.cache import MarketDataCache, TTLLRUCache
from pnlclaw_market.event_bus import EventBus
from pnlclaw_market.service import (
    MarketDataService,
    MarketDataServiceError,
    MarketDataServiceNotRunning,
)
from pnlclaw_market.snapshot_store import SnapshotStore
from pnlclaw_market.state_engine import (
    InsufficientDataError,
    MarketStateEngine,
)
from pnlclaw_market.stream_manager import StreamManager, StreamType

__all__ = [
    "EventBus",
    "InsufficientDataError",
    "MarketDataCache",
    "MarketDataService",
    "MarketDataServiceError",
    "MarketDataServiceNotRunning",
    "MarketStateEngine",
    "SnapshotStore",
    "StreamManager",
    "StreamType",
    "TTLLRUCache",
]
