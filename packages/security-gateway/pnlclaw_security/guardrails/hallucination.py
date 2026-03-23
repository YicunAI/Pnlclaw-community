"""AI hallucination detection guardrail.

Detects when AI references prices or indicators that deviate significantly
from actual market data. Source: distillation-plan-supplement-3 gap 20.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from pnlclaw_types import RiskLevel

# ---------------------------------------------------------------------------
# Alert model
# ---------------------------------------------------------------------------


class PriceDeviationAlert(BaseModel):
    """Alert raised when AI-referenced price deviates from actual."""

    symbol: str
    ai_price: float
    actual_price: float
    deviation_pct: float = Field(description="Absolute deviation as fraction (0.10 = 10%)")
    threshold_pct: float
    severity: RiskLevel
    message: str = ""


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

# Graduated severity thresholds
_SEVERITY_THRESHOLDS: list[tuple[float, RiskLevel]] = [
    (0.50, RiskLevel.BLOCKED),  # >50% deviation
    (0.25, RiskLevel.DANGEROUS),  # >25% deviation
    (0.10, RiskLevel.RESTRICTED),  # >10% deviation
]

# Known indicator names (extensible)
KNOWN_INDICATORS: frozenset[str] = frozenset(
    {
        "sma",
        "ema",
        "rsi",
        "macd",
        "macd_signal",
        "macd_histogram",
        "bollinger_upper",
        "bollinger_middle",
        "bollinger_lower",
        "atr",
        "adx",
        "cci",
        "stochastic_k",
        "stochastic_d",
        "williams_r",
        "obv",
        "vwap",
        "ichimoku_tenkan",
        "ichimoku_kijun",
        "ichimoku_senkou_a",
        "ichimoku_senkou_b",
    }
)


class HallucinationDetector:
    """Detect AI hallucinations in trading context.

    Checks:
    - Price references that deviate from actual market prices
    - References to non-existent indicators
    - Unreasonable confidence levels

    Args:
        price_deviation_threshold: Minimum deviation to trigger an alert.
            Default 0.10 (10%).
    """

    def __init__(self, price_deviation_threshold: float = 0.10) -> None:
        self._threshold = price_deviation_threshold

    def check_price_reference(
        self,
        symbol: str,
        ai_referenced_price: float,
        actual_price: float,
    ) -> PriceDeviationAlert | None:
        """Check if an AI-referenced price deviates from the actual price.

        Args:
            symbol: Trading pair symbol.
            ai_referenced_price: Price mentioned by the AI.
            actual_price: Current market price.

        Returns:
            :class:`PriceDeviationAlert` if deviation exceeds threshold,
            ``None`` otherwise.
        """
        if actual_price <= 0:
            # Cannot compute deviation; flag as suspicious
            return PriceDeviationAlert(
                symbol=symbol,
                ai_price=ai_referenced_price,
                actual_price=actual_price,
                deviation_pct=1.0,
                threshold_pct=self._threshold,
                severity=RiskLevel.DANGEROUS,
                message=f"Actual price for {symbol} is non-positive ({actual_price})",
            )

        deviation = abs(ai_referenced_price - actual_price) / actual_price

        if deviation < self._threshold:
            return None

        # Determine severity
        severity = RiskLevel.RESTRICTED
        for threshold, level in _SEVERITY_THRESHOLDS:
            if deviation >= threshold:
                severity = level
                break

        return PriceDeviationAlert(
            symbol=symbol,
            ai_price=ai_referenced_price,
            actual_price=actual_price,
            deviation_pct=round(deviation, 4),
            threshold_pct=self._threshold,
            severity=severity,
            message=(
                f"AI referenced price {ai_referenced_price} for {symbol} "
                f"deviates {deviation:.1%} from actual {actual_price}"
            ),
        )

    def check_indicator_exists(
        self,
        indicator_name: str,
        known: frozenset[str] | None = None,
    ) -> bool:
        """Check if an indicator name is known.

        Returns ``True`` if the indicator exists, ``False`` if it appears
        to be fabricated by the AI.
        """
        known_set = known or KNOWN_INDICATORS
        return indicator_name.strip().lower() in known_set

    def check_confidence_reasonable(
        self,
        confidence: float,
        *,
        max_confidence: float = 0.99,
    ) -> bool:
        """Check if a confidence level is within a reasonable range.

        Extremely high confidence (>0.99) is suspicious for market predictions.

        Returns ``True`` if reasonable, ``False`` if suspiciously high.
        """
        return 0.0 <= confidence <= max_confidence
