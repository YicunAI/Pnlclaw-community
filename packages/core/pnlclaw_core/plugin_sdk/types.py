"""Plugin capability type definitions — Protocols and ABCs for plugin contracts."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExchangeAdapter(Protocol):
    """Protocol for exchange adapters (WebSocket + REST)."""

    @property
    def name(self) -> str:
        """Exchange identifier (e.g. 'binance')."""
        ...

    async def connect(self) -> None:
        """Establish connection to the exchange."""
        ...

    async def disconnect(self) -> None:
        """Close the connection."""
        ...

    async def subscribe(self, symbol: str, channel: str) -> None:
        """Subscribe to a data channel for a symbol."""
        ...

    async def unsubscribe(self, symbol: str, channel: str) -> None:
        """Unsubscribe from a data channel."""
        ...


@runtime_checkable
class StrategyPlugin(Protocol):
    """Protocol for strategy plugins."""

    @property
    def name(self) -> str:
        """Strategy identifier."""
        ...

    def validate(self, config: dict[str, Any]) -> list[str]:
        """Validate strategy configuration. Returns list of errors (empty = valid)."""
        ...

    def on_kline(self, kline: dict[str, Any]) -> dict[str, Any] | None:
        """Process a kline event, optionally returning a signal."""
        ...


@runtime_checkable
class IndicatorPlugin(Protocol):
    """Protocol for technical indicator plugins."""

    @property
    def name(self) -> str:
        """Indicator name (e.g. 'sma')."""
        ...

    def calculate(self, data: Any) -> Any:
        """Calculate indicator values from input data (e.g. pd.DataFrame → pd.Series)."""
        ...


@runtime_checkable
class LLMProviderPlugin(Protocol):
    """Protocol for LLM provider plugins."""

    @property
    def name(self) -> str:
        """Provider name (e.g. 'openai')."""
        ...

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Send a chat completion request."""
        ...

    async def chat_stream(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        """Send a streaming chat completion request."""
        ...


@runtime_checkable
class ToolPlugin(Protocol):
    """Protocol for agent tool plugins."""

    @property
    def name(self) -> str:
        """Tool name."""
        ...

    @property
    def description(self) -> str:
        """Human-readable tool description."""
        ...

    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with given arguments."""
        ...
