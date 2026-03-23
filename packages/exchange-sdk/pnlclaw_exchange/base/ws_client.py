"""Abstract base class for exchange WebSocket clients.

All exchange WebSocket adapters must extend :class:`BaseWSClient` and implement
the four abstract methods: :meth:`connect`, :meth:`subscribe`,
:meth:`unsubscribe`, and :meth:`close`.

The base class tracks active subscriptions so the reconnect manager can
restore them after a reconnection.
"""

from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pnlclaw_exchange.types import WSClientConfig

logger = logging.getLogger(__name__)

# Type alias for callbacks that accept both sync and async callables.
Callback = Callable[..., Any]


class BaseWSClient(ABC):
    """Abstract WebSocket client for exchange market data streams.

    Subclasses implement exchange-specific connection establishment, message
    parsing, and stream-name construction.

    Contract:
        - All I/O methods are ``async``.
        - Event delivery is callback-based: ``on_message``, ``on_error``,
          ``on_connect``, ``on_disconnect``.
        - Active subscriptions are tracked in ``_subscriptions`` for
          reconnection recovery.
    """

    def __init__(
        self,
        config: WSClientConfig,
        *,
        on_message: Callback | None = None,
        on_error: Callback | None = None,
        on_connect: Callback | None = None,
        on_disconnect: Callback | None = None,
    ) -> None:
        self._config = config
        self._subscriptions: set[str] = set()
        self._is_connected: bool = False

        # Public callbacks – may be reassigned after construction.
        self.on_message = on_message
        self.on_error = on_error
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect

    # ------------------------------------------------------------------
    # Abstract interface – must be implemented by subclasses
    # ------------------------------------------------------------------

    @abstractmethod
    async def connect(self) -> None:
        """Establish the WebSocket connection.

        Implementations must call :meth:`_dispatch_connect` on success.
        """

    @abstractmethod
    async def subscribe(self, streams: list[str]) -> None:
        """Subscribe to the given streams.

        Implementations must add the stream names to ``_subscriptions``.
        """

    @abstractmethod
    async def unsubscribe(self, streams: list[str]) -> None:
        """Unsubscribe from the given streams.

        Implementations must remove the stream names from ``_subscriptions``.
        """

    @abstractmethod
    async def close(self) -> None:
        """Close the WebSocket connection gracefully.

        Implementations must call :meth:`_dispatch_disconnect`.
        """

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def subscriptions(self) -> frozenset[str]:
        """Return a frozen copy of the currently active subscriptions."""
        return frozenset(self._subscriptions)

    @property
    def is_connected(self) -> bool:
        """Whether the WebSocket connection is currently open."""
        return self._is_connected

    @property
    def config(self) -> WSClientConfig:
        """Return the client configuration."""
        return self._config

    # ------------------------------------------------------------------
    # Dispatch helpers – call the user-supplied callbacks
    # ------------------------------------------------------------------

    async def _dispatch_message(self, data: dict[str, Any]) -> None:
        """Dispatch a parsed message to the ``on_message`` callback."""
        await self._invoke(self.on_message, data)

    async def _dispatch_error(self, error: Exception) -> None:
        """Dispatch an error to the ``on_error`` callback."""
        await self._invoke(self.on_error, error)

    async def _dispatch_connect(self) -> None:
        """Mark the client as connected and invoke ``on_connect``."""
        self._is_connected = True
        logger.info("WebSocket connected to %s (%s)", self._config.url, self._config.exchange)
        await self._invoke(self.on_connect)

    async def _dispatch_disconnect(self, code: int = 1000, reason: str = "") -> None:
        """Mark the client as disconnected and invoke ``on_disconnect``."""
        self._is_connected = False
        logger.info(
            "WebSocket disconnected from %s (code=%d, reason=%s)",
            self._config.url,
            code,
            reason,
        )
        await self._invoke(self.on_disconnect, code, reason)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _invoke(callback: Callback | None, *args: Any) -> None:
        """Invoke a callback, handling both sync and async callables."""
        if callback is None:
            return
        result = callback(*args)
        if inspect.isawaitable(result):
            await result
