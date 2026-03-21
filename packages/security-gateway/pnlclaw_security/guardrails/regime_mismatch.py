"""Market regime mismatch detection guardrail.

Detects when a strategy's preferred market conditions don't match
the current market state. Source: distillation-plan-supplement-3 gap 20.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from pnlclaw_types import MarketRegime, RiskLevel, StrategyType

# ---------------------------------------------------------------------------
# Compatibility matrix
# ---------------------------------------------------------------------------

STRATEGY_REGIME_COMPAT: dict[StrategyType, set[MarketRegime]] = {
    StrategyType.SMA_CROSS: {MarketRegime.TRENDING},
    StrategyType.RSI_REVERSAL: {MarketRegime.RANGING},
    StrategyType.MACD: {MarketRegime.TRENDING, MarketRegime.VOLATILE},
    StrategyType.CUSTOM: {MarketRegime.TRENDING, MarketRegime.RANGING, MarketRegime.VOLATILE},
}

# ---------------------------------------------------------------------------
# Alert model
# ---------------------------------------------------------------------------


class RegimeMismatchAlert(BaseModel):
    """Alert raised when strategy type doesn't match current market regime."""

    strategy_name: str = ""
    strategy_type: StrategyType
    current_regime: MarketRegime
    expected_regimes: list[MarketRegime]
    severity: RiskLevel
    message: str


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class RegimeMismatchDetector:
    """Detect mismatches between strategy type and current market regime.

    Uses a compatibility matrix mapping each :class:`StrategyType` to its
    preferred :class:`MarketRegime` set. Mismatches produce warnings or
    danger-level alerts depending on how strong the mismatch is.

    Args:
        custom_compat: Override the default compatibility matrix.
    """

    def __init__(
        self,
        custom_compat: dict[StrategyType, set[MarketRegime]] | None = None,
    ) -> None:
        self._compat = custom_compat or dict(STRATEGY_REGIME_COMPAT)

    def check_mismatch(
        self,
        strategy_type: StrategyType,
        current_regime: MarketRegime,
        *,
        trend_strength: float = 0.5,
        volatility: float = 0.5,
        strategy_name: str = "",
    ) -> RegimeMismatchAlert | None:
        """Check if a strategy type is compatible with the current regime.

        Args:
            strategy_type: The strategy classification.
            current_regime: Current market regime.
            trend_strength: 0-1 measure of trend strength (higher = stronger trend).
            volatility: 0-1 measure of volatility (higher = more volatile).
            strategy_name: Optional name for the alert message.

        Returns:
            :class:`RegimeMismatchAlert` if mismatch detected, ``None`` otherwise.
        """
        expected = self._compat.get(
            strategy_type,
            # Unknown types get all regimes (permissive default)
            {MarketRegime.TRENDING, MarketRegime.RANGING, MarketRegime.VOLATILE},
        )

        if current_regime in expected:
            return None

        # Determine severity based on strength of mismatch
        severity = self._assess_severity(
            strategy_type, current_regime, trend_strength, volatility
        )

        return RegimeMismatchAlert(
            strategy_name=strategy_name,
            strategy_type=strategy_type,
            current_regime=current_regime,
            expected_regimes=sorted(expected, key=lambda r: r.value),
            severity=severity,
            message=self._build_message(
                strategy_name or strategy_type.value,
                strategy_type,
                current_regime,
                expected,
                trend_strength,
                volatility,
            ),
        )

    def check_volatility_mismatch(
        self,
        strategy_type: StrategyType,
        volatility: float,
        *,
        max_volatility: float = 0.8,
        strategy_name: str = "",
    ) -> RegimeMismatchAlert | None:
        """Check if volatility is too high for strategies that don't handle it.

        Args:
            strategy_type: The strategy classification.
            volatility: Current volatility measure (0-1).
            max_volatility: Threshold above which to warn.
            strategy_name: Optional name for the alert message.

        Returns:
            Alert if volatility is too high for the strategy type.
        """
        volatile_compatible = self._compat.get(strategy_type, set())
        if MarketRegime.VOLATILE in volatile_compatible:
            return None

        if volatility <= max_volatility:
            return None

        return RegimeMismatchAlert(
            strategy_name=strategy_name,
            strategy_type=strategy_type,
            current_regime=MarketRegime.VOLATILE,
            expected_regimes=sorted(
                self._compat.get(strategy_type, set()), key=lambda r: r.value
            ),
            severity=RiskLevel.RESTRICTED,
            message=(
                f"High volatility ({volatility:.2f}) detected but strategy "
                f"{strategy_name or strategy_type.value} is not designed for "
                f"volatile conditions"
            ),
        )

    # -- internal ------------------------------------------------------------

    @staticmethod
    def _assess_severity(
        strategy_type: StrategyType,
        current_regime: MarketRegime,
        trend_strength: float,
        volatility: float,
    ) -> RiskLevel:
        """Determine severity of a regime mismatch."""
        # Strong mismatch: trend strategy in strongly ranging market (or vice versa)
        if (
            strategy_type in (StrategyType.SMA_CROSS,)
            and current_regime == MarketRegime.RANGING
            and trend_strength < 0.3
        ):
            return RiskLevel.DANGEROUS

        if (
            strategy_type == StrategyType.RSI_REVERSAL
            and current_regime == MarketRegime.TRENDING
            and trend_strength > 0.7
        ):
            return RiskLevel.DANGEROUS

        # High volatility + strategy not designed for it
        if current_regime == MarketRegime.VOLATILE and volatility > 0.8:
            return RiskLevel.DANGEROUS

        return RiskLevel.RESTRICTED

    @staticmethod
    def _build_message(
        name: str,
        strategy_type: StrategyType,
        current_regime: MarketRegime,
        expected: set[MarketRegime],
        trend_strength: float,
        volatility: float,
    ) -> str:
        expected_str = "/".join(r.value for r in sorted(expected, key=lambda r: r.value))
        return (
            f"Strategy '{name}' ({strategy_type.value}) is designed for "
            f"{expected_str} markets, but current regime is {current_regime.value} "
            f"(trend_strength={trend_strength:.2f}, volatility={volatility:.2f})"
        )
