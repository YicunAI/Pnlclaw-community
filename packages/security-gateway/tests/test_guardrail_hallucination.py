"""Tests for pnlclaw_security.guardrails.hallucination."""

from pnlclaw_types import RiskLevel

from pnlclaw_security.guardrails.hallucination import (
    HallucinationDetector,
    KNOWN_INDICATORS,
)


class TestPriceDeviation:
    def test_no_alert_within_threshold(self) -> None:
        detector = HallucinationDetector()
        result = detector.check_price_reference("BTC/USDT", 50_500, 50_000)
        assert result is None  # 1% deviation, below 10% threshold

    def test_alert_at_10pct(self) -> None:
        detector = HallucinationDetector()
        result = detector.check_price_reference("BTC/USDT", 55_500, 50_000)
        assert result is not None
        assert result.severity == RiskLevel.RESTRICTED
        assert result.deviation_pct >= 0.10

    def test_alert_at_25pct(self) -> None:
        detector = HallucinationDetector()
        result = detector.check_price_reference("BTC/USDT", 62_500, 50_000)
        assert result is not None
        assert result.severity == RiskLevel.DANGEROUS

    def test_alert_at_50pct(self) -> None:
        detector = HallucinationDetector()
        result = detector.check_price_reference("BTC/USDT", 75_000, 50_000)
        assert result is not None
        assert result.severity == RiskLevel.BLOCKED

    def test_zero_actual_price(self) -> None:
        detector = HallucinationDetector()
        result = detector.check_price_reference("BTC/USDT", 100, 0)
        assert result is not None
        assert result.severity == RiskLevel.DANGEROUS

    def test_negative_actual_price(self) -> None:
        detector = HallucinationDetector()
        result = detector.check_price_reference("BTC/USDT", 100, -10)
        assert result is not None

    def test_exact_price_no_alert(self) -> None:
        detector = HallucinationDetector()
        result = detector.check_price_reference("BTC/USDT", 50_000, 50_000)
        assert result is None

    def test_custom_threshold(self) -> None:
        detector = HallucinationDetector(price_deviation_threshold=0.05)
        # 8% deviation should trigger with 5% threshold
        result = detector.check_price_reference("BTC/USDT", 54_000, 50_000)
        assert result is not None

    def test_below_deviation(self) -> None:
        detector = HallucinationDetector()
        # 9.9% should NOT trigger (below 10%)
        result = detector.check_price_reference("BTC/USDT", 54_950, 50_000)
        assert result is None

    def test_message_content(self) -> None:
        detector = HallucinationDetector()
        result = detector.check_price_reference("ETH/USDT", 4_000, 3_000)
        assert result is not None
        assert "ETH/USDT" in result.message
        assert "4000" in result.message


class TestIndicatorExists:
    def test_known_indicators(self) -> None:
        detector = HallucinationDetector()
        for name in ["sma", "ema", "rsi", "macd", "atr", "adx"]:
            assert detector.check_indicator_exists(name) is True

    def test_unknown_indicator(self) -> None:
        detector = HallucinationDetector()
        assert detector.check_indicator_exists("quantum_momentum_flux") is False

    def test_case_insensitive(self) -> None:
        detector = HallucinationDetector()
        assert detector.check_indicator_exists("RSI") is True
        assert detector.check_indicator_exists("MACD") is True

    def test_custom_known_set(self) -> None:
        detector = HallucinationDetector()
        custom = frozenset({"custom_indicator"})
        assert detector.check_indicator_exists("custom_indicator", known=custom) is True
        assert detector.check_indicator_exists("sma", known=custom) is False


class TestConfidenceReasonable:
    def test_normal_confidence(self) -> None:
        detector = HallucinationDetector()
        assert detector.check_confidence_reasonable(0.75) is True

    def test_zero_confidence(self) -> None:
        detector = HallucinationDetector()
        assert detector.check_confidence_reasonable(0.0) is True

    def test_suspiciously_high(self) -> None:
        detector = HallucinationDetector()
        assert detector.check_confidence_reasonable(1.0) is False

    def test_custom_max(self) -> None:
        detector = HallucinationDetector()
        assert detector.check_confidence_reasonable(0.95, max_confidence=0.90) is False
