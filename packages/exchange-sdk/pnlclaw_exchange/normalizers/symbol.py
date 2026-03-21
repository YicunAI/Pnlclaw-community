"""Symbol normalization between exchange-native and unified formats.

Provides a registry-based approach where each exchange registers its own
symbol normalization rule. Binance is registered by default.

Example::

    normalizer = SymbolNormalizer()
    normalizer.to_unified("binance", "BTCUSDT")   # → "BTC/USDT"
    normalizer.to_exchange("binance", "BTC/USDT")  # → "BTCUSDT"
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from pnlclaw_types.errors import ValidationError

logger = logging.getLogger(__name__)


@runtime_checkable
class ExchangeSymbolRule(Protocol):
    """Per-exchange symbol normalization rule.

    Implementations convert between exchange-native symbols (e.g. ``BTCUSDT``)
    and PnLClaw's unified format (e.g. ``BTC/USDT``).
    """

    def to_unified(self, raw_symbol: str) -> str:
        """Convert exchange-native symbol to unified ``BASE/QUOTE`` format."""
        ...

    def to_exchange(self, unified_symbol: str) -> str:
        """Convert unified ``BASE/QUOTE`` format to exchange-native symbol."""
        ...


class _BinanceSymbolRule:
    """Binance symbol rule: ``BTCUSDT`` → ``BTC/USDT``.

    Splits by known quote currencies, trying longer matches first to avoid
    ambiguity (e.g. ``BTCUSDT`` should not match ``BTC`` as the quote).
    """

    # Ordered by length descending to prevent partial matches.
    KNOWN_QUOTES: tuple[str, ...] = (
        "FDUSD",
        "USDT",
        "BUSD",
        "USDC",
        "TUSD",
        "BTC",
        "ETH",
        "BNB",
    )

    def to_unified(self, raw_symbol: str) -> str:
        upper = raw_symbol.upper()
        for quote in self.KNOWN_QUOTES:
            if upper.endswith(quote):
                base = upper[: -len(quote)]
                if base:
                    return f"{base}/{quote}"
        raise ValidationError(
            f"Cannot normalize Binance symbol: {raw_symbol!r}",
            details={"raw_symbol": raw_symbol},
        )

    def to_exchange(self, unified_symbol: str) -> str:
        if "/" not in unified_symbol:
            return unified_symbol.upper()
        base, quote = unified_symbol.split("/", 1)
        return f"{base}{quote}".upper()


class SymbolNormalizer:
    """Registry of per-exchange symbol normalization rules.

    Contract:
        - :meth:`to_unified` converts exchange-native to ``BASE/QUOTE``.
        - :meth:`to_exchange` converts ``BASE/QUOTE`` to exchange-native.
        - New exchanges are added via :meth:`register`, without modifying core.
        - Binance is registered by default.
    """

    def __init__(self) -> None:
        self._rules: dict[str, ExchangeSymbolRule] = {}
        self.register("binance", _BinanceSymbolRule())

    def register(self, exchange: str, rule: ExchangeSymbolRule) -> None:
        """Register a symbol normalization rule for an exchange.

        Args:
            exchange: Exchange identifier (e.g. ``"binance"``).
            rule: Object implementing :class:`ExchangeSymbolRule`.
        """
        self._rules[exchange.lower()] = rule

    def to_unified(self, exchange: str, raw_symbol: str) -> str:
        """Convert an exchange-native symbol to unified format.

        Args:
            exchange: Exchange identifier.
            raw_symbol: Exchange-native symbol (e.g. ``"BTCUSDT"``).

        Returns:
            Unified symbol (e.g. ``"BTC/USDT"``).

        Raises:
            ValidationError: If the exchange is not registered or the symbol
                cannot be normalized.
        """
        rule = self._get_rule(exchange)
        return rule.to_unified(raw_symbol)

    def to_exchange(self, exchange: str, unified_symbol: str) -> str:
        """Convert a unified symbol to exchange-native format.

        Args:
            exchange: Exchange identifier.
            unified_symbol: Unified symbol (e.g. ``"BTC/USDT"``).

        Returns:
            Exchange-native symbol (e.g. ``"BTCUSDT"``).

        Raises:
            ValidationError: If the exchange is not registered.
        """
        rule = self._get_rule(exchange)
        return rule.to_exchange(unified_symbol)

    def _get_rule(self, exchange: str) -> ExchangeSymbolRule:
        key = exchange.lower()
        if key not in self._rules:
            raise ValidationError(
                f"No symbol rule registered for exchange: {exchange!r}",
                details={"exchange": exchange},
            )
        return self._rules[key]
