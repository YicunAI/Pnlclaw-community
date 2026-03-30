"""AI hallucination detection guardrail.

Detects when AI references prices or indicators that deviate significantly
from actual market data. Source: distillation-plan-supplement-3 gap 20.
Extended in v0.1.1 with financial claim scanning, investment promise
detection, and output secret redaction.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from pnlclaw_types import RiskLevel

logger = logging.getLogger(__name__)

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

    # ------------------------------------------------------------------
    # v0.1.1: Financial output scanning
    # ------------------------------------------------------------------

    def scan_text_for_unverified_claims(
        self,
        text: str,
        tool_results: list[dict[str, Any]],
    ) -> ScanResult:
        """Detect numeric claims in text not supported by tool results.

        Extracts price-like numbers ($1,234.56), percentages (23.5%),
        and named metrics (Sharpe 1.8) from the AI output, then cross-
        references them against ``tool_results`` data.
        """
        result = ScanResult()
        claims = _extract_numeric_claims(text)

        if not claims:
            return result

        tool_text = _flatten_tool_results(tool_results)

        for claim in claims:
            if not _claim_supported_by_tools(claim, tool_text):
                result.warnings.append(f"⚠️ 此数据未经工具验证: {claim}")
                result.triggered = True
                logger.warning("hallucination_detected", extra={
                    "type": "unverified_claim",
                    "matched_text": claim,
                    "action": "appended_warning",
                })

        return result

    def scan_for_investment_promises(self, text: str) -> ScanResult:
        """Detect investment promise language (Chinese and English)."""
        result = ScanResult()

        for pattern in _INVESTMENT_PROMISE_PATTERNS:
            match = pattern.search(text)
            if match:
                result.warnings.append(
                    "⚠️ 投资有风险，过往表现不预示未来收益 / "
                    "Investment involves risk; past performance does not guarantee future results."
                )
                result.triggered = True
                logger.warning("hallucination_detected", extra={
                    "type": "investment_promise",
                    "matched_text": match.group(0),
                    "action": "appended_disclaimer",
                })
                break  # One disclaimer is enough

        return result

    def redact_secrets_in_output(self, text: str) -> str:
        """Strip secrets from AI output using the redaction engine."""
        from pnlclaw_security.redaction import redact_text

        redacted = redact_text(text)
        if redacted != text:
            logger.warning("hallucination_detected", extra={
                "type": "secret_leak",
                "matched_text": "[redacted content]",
                "action": "redacted",
            })
        return redacted

    def scan_output(
        self,
        text: str,
        tool_results: list[dict[str, Any]] | None = None,
    ) -> tuple[str, ScanResult]:
        """Run all scans on AI output and return annotated text + result.

        This is the single entry-point used by the ReAct Answer stage.

        Scan tiers:
        1. Secret redaction — always applied (mutates text)
        2. Unverified numeric claims — logged internally only, NOT shown to users
           (derived calculations like spread%, change% are expected analyst behavior)
        3. Investment promises — appended as visible disclaimer
        """
        combined = ScanResult()

        # 1. Secret redaction (always first, mutates text)
        text = self.redact_secrets_in_output(text)

        # 2. Unverified claims — internal logging only
        if tool_results is not None:
            claim_result = self.scan_text_for_unverified_claims(text, tool_results)
            if claim_result.triggered:
                combined.triggered = True

        # 3. Investment promises — user-visible disclaimer
        promise_result = self.scan_for_investment_promises(text)
        if promise_result.triggered:
            combined.merge(promise_result)

        if combined.warnings:
            text = text + "\n\n" + "\n".join(combined.warnings)

        return text, combined


# ---------------------------------------------------------------------------
# ScanResult
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    """Result of a hallucination scan pass."""

    triggered: bool = False
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: ScanResult) -> None:
        if other.triggered:
            self.triggered = True
        self.warnings.extend(other.warnings)


# ---------------------------------------------------------------------------
# Numeric claim extraction
# ---------------------------------------------------------------------------

_PRICE_RE = re.compile(r"\$[\d,]+(?:\.\d+)?")
_PERCENTAGE_RE = re.compile(r"\d+(?:\.\d+)?%")
_METRIC_RE = re.compile(
    r"\b(?:Sharpe|Sortino|Calmar|drawdown|max drawdown|volatility|APY|APR)"
    r"\s*(?:ratio|of)?\s*[:=]?\s*([\d.]+)",
    re.IGNORECASE,
)


def _extract_numeric_claims(text: str) -> list[str]:
    """Extract price, percentage, and metric claims from text."""
    claims: list[str] = []
    claims.extend(m.group(0) for m in _PRICE_RE.finditer(text))
    claims.extend(m.group(0) for m in _PERCENTAGE_RE.finditer(text))
    claims.extend(m.group(0) for m in _METRIC_RE.finditer(text))
    return claims


def _flatten_tool_results(tool_results: list[dict[str, Any]]) -> str:
    """Flatten tool results into a single string for matching."""
    import json

    parts: list[str] = []
    for tr in tool_results:
        output = tr.get("output", "")
        result = tr.get("result", "")
        if isinstance(output, str):
            parts.append(output)
        elif isinstance(output, dict):
            parts.append(json.dumps(output))
        if isinstance(result, str):
            parts.append(result)
        elif isinstance(result, dict):
            parts.append(json.dumps(result))
    return " ".join(parts)


def _claim_supported_by_tools(claim: str, tool_text: str) -> bool:
    """Check if a numeric claim is supported by tool result data.

    Uses three tiers:
    1. Exact match in tool text → supported
    2. Small percentages (< 10%) → assumed derived calculation, supported
    3. Price-like values → fuzzy match within 1% of any price in tool text
    """
    cleaned = claim.replace("$", "").replace(",", "").replace("%", "").strip()

    if cleaned in tool_text or claim in tool_text:
        return True

    if claim.endswith("%"):
        try:
            pct_val = float(cleaned)
            if abs(pct_val) < 10.0:
                return True
        except ValueError:
            pass

    if claim.startswith("$") or (cleaned.replace(".", "", 1).isdigit() and float(cleaned) > 100):
        try:
            claimed_val = float(cleaned)
            for num_match in re.finditer(r"[\d,]+(?:\.\d+)?", tool_text):
                try:
                    tool_val = float(num_match.group(0).replace(",", ""))
                    if tool_val > 0 and abs(claimed_val - tool_val) / tool_val < 0.01:
                        return True
                except ValueError:
                    continue
        except ValueError:
            pass

    return False


# ---------------------------------------------------------------------------
# Investment promise patterns
# ---------------------------------------------------------------------------

_INVESTMENT_PROMISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"保证盈利",
        r"稳赚",
        r"零风险",
        r"必涨",
        r"翻倍",
        r"保本",
        r"guarantee[sd]?\s+returns?",
        r"risk[\s-]*free",
        r"sure\s+profit",
        r"can'?t\s+lose",
        r"guarantee[sd]?\s+profits?",
    ]
]
