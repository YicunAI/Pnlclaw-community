"""PnLClaw Plugin API — the interface plugins use to register capabilities."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PnLClawPluginAPI(Protocol):
    """Plugin API interface with 12 registration methods.

    Plugins receive an instance of this protocol and call register_*
    methods to declare their capabilities during initialization.
    """

    def register_exchange(self, name: str, adapter: Any) -> None:
        """Register an exchange adapter (WebSocket + REST).

        Args:
            name: Unique exchange identifier (e.g. 'binance').
            adapter: ExchangeAdapter implementation.
        """
        ...

    def register_strategy(self, name: str, strategy: Any) -> None:
        """Register a strategy plugin.

        Args:
            name: Unique strategy identifier.
            strategy: StrategyPlugin implementation.
        """
        ...

    def register_indicator(self, name: str, indicator: Any) -> None:
        """Register a technical indicator.

        Args:
            name: Indicator name (e.g. 'sma', 'ema', 'rsi').
            indicator: IndicatorPlugin implementation.
        """
        ...

    def register_llm_provider(self, name: str, provider: Any) -> None:
        """Register an LLM provider.

        Args:
            name: Provider name (e.g. 'openai', 'ollama').
            provider: LLMProviderPlugin implementation.
        """
        ...

    def register_channel(self, name: str, channel: Any) -> None:
        """Register a messaging channel (e.g. Telegram, Discord).

        Args:
            name: Channel name.
            channel: ChannelPlugin implementation.
        """
        ...

    def register_tool(self, name: str, tool: Any) -> None:
        """Register an agent tool.

        Args:
            name: Tool name (e.g. 'market_ticker').
            tool: Tool implementation with execute() method.
        """
        ...

    def register_hook(self, event: str, handler: Any, *, priority: int = 0) -> None:
        """Register a hook handler for an internal event.

        Args:
            event: Event name (e.g. 'on_market_tick').
            handler: Callable hook handler.
            priority: Execution priority (higher = earlier).
        """
        ...

    def register_risk_rule(self, name: str, rule: Any) -> None:
        """Register a risk control rule.

        Args:
            name: Rule identifier.
            rule: RiskRule implementation.
        """
        ...

    def register_metric(self, name: str, metric_type: str, description: str) -> None:
        """Register a custom metric.

        Args:
            name: Metric name (e.g. 'pnlclaw.plugin.requests').
            metric_type: One of 'counter', 'gauge', 'histogram'.
            description: Human-readable description.
        """
        ...

    def register_health_check(self, name: str, check: Any) -> None:
        """Register a health check function.

        Args:
            name: Check name (e.g. 'binance_ws').
            check: Async callable returning health status.
        """
        ...

    def register_command(self, name: str, handler: Any) -> None:
        """Register a CLI command.

        Args:
            name: Command name (e.g. 'exchange-setup').
            handler: Command handler callable.
        """
        ...

    def register_middleware(self, name: str, middleware: Any) -> None:
        """Register API middleware.

        Args:
            name: Middleware identifier.
            middleware: ASGI middleware factory.
        """
        ...
