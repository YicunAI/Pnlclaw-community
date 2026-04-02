"""Tests for pnlclaw_security.guardrails.regime_mismatch."""

from pnlclaw_security.guardrails.regime_mismatch import (
    STRATEGY_REGIME_COMPAT,
    RegimeMismatchDetector,
)
from pnlclaw_types import MarketRegime, RiskLevel, StrategyType


class TestCompatibilityMatrix:
    def test_sma_cross_prefers_trending(self) -> None:
        assert MarketRegime.TRENDING in STRATEGY_REGIME_COMPAT[StrategyType.SMA_CROSS]
        assert MarketRegime.RANGING not in STRATEGY_REGIME_COMPAT[StrategyType.SMA_CROSS]

    def test_rsi_reversal_prefers_ranging(self) -> None:
        assert MarketRegime.RANGING in STRATEGY_REGIME_COMPAT[StrategyType.RSI_REVERSAL]
        assert MarketRegime.TRENDING not in STRATEGY_REGIME_COMPAT[StrategyType.RSI_REVERSAL]

    def test_macd_handles_trending_and_volatile(self) -> None:
        assert MarketRegime.TRENDING in STRATEGY_REGIME_COMPAT[StrategyType.MACD]
        assert MarketRegime.VOLATILE in STRATEGY_REGIME_COMPAT[StrategyType.MACD]

    def test_custom_is_permissive(self) -> None:
        custom = STRATEGY_REGIME_COMPAT[StrategyType.CUSTOM]
        assert len(custom) == 3  # All regimes


class TestCheckMismatch:
    def test_sma_cross_in_trending_ok(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_mismatch(StrategyType.SMA_CROSS, MarketRegime.TRENDING)
        assert result is None

    def test_sma_cross_in_ranging_alerts(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_mismatch(StrategyType.SMA_CROSS, MarketRegime.RANGING)
        assert result is not None
        assert result.strategy_type == StrategyType.SMA_CROSS
        assert result.current_regime == MarketRegime.RANGING
        assert MarketRegime.TRENDING in result.expected_regimes

    def test_rsi_reversal_in_trending_alerts(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_mismatch(StrategyType.RSI_REVERSAL, MarketRegime.TRENDING)
        assert result is not None

    def test_rsi_reversal_in_ranging_ok(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_mismatch(StrategyType.RSI_REVERSAL, MarketRegime.RANGING)
        assert result is None

    def test_custom_always_ok(self) -> None:
        detector = RegimeMismatchDetector()
        for regime in MarketRegime:
            result = detector.check_mismatch(StrategyType.CUSTOM, regime)
            assert result is None

    def test_strategy_name_in_message(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_mismatch(
            StrategyType.SMA_CROSS,
            MarketRegime.RANGING,
            strategy_name="My SMA Strategy",
        )
        assert result is not None
        assert "My SMA Strategy" in result.message


class TestSeverity:
    def test_strong_mismatch_sma_in_ranging(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_mismatch(
            StrategyType.SMA_CROSS,
            MarketRegime.RANGING,
            trend_strength=0.2,  # Very weak trend = strong mismatch
        )
        assert result is not None
        assert result.severity == RiskLevel.DANGEROUS

    def test_mild_mismatch_sma_in_ranging(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_mismatch(
            StrategyType.SMA_CROSS,
            MarketRegime.RANGING,
            trend_strength=0.5,  # Moderate trend = mild mismatch
        )
        assert result is not None
        assert result.severity == RiskLevel.RESTRICTED

    def test_strong_mismatch_rsi_in_trending(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_mismatch(
            StrategyType.RSI_REVERSAL,
            MarketRegime.TRENDING,
            trend_strength=0.8,  # Strong trend = strong mismatch for mean-reversion
        )
        assert result is not None
        assert result.severity == RiskLevel.DANGEROUS

    def test_high_volatility_mismatch(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_mismatch(
            StrategyType.SMA_CROSS,
            MarketRegime.VOLATILE,
            volatility=0.9,
        )
        assert result is not None
        assert result.severity == RiskLevel.DANGEROUS


class TestVolatilityMismatch:
    def test_volatile_compatible_no_alert(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_volatility_mismatch(StrategyType.MACD, volatility=0.95)
        assert result is None  # MACD handles volatility

    def test_not_volatile_compatible_alerts(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_volatility_mismatch(StrategyType.RSI_REVERSAL, volatility=0.9)
        assert result is not None
        assert "volatility" in result.message.lower()

    def test_below_threshold_no_alert(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_volatility_mismatch(StrategyType.RSI_REVERSAL, volatility=0.5)
        assert result is None

    def test_custom_threshold(self) -> None:
        detector = RegimeMismatchDetector()
        result = detector.check_volatility_mismatch(StrategyType.SMA_CROSS, volatility=0.6, max_volatility=0.5)
        assert result is not None


class TestCustomCompat:
    def test_override_matrix(self) -> None:
        custom = {
            StrategyType.SMA_CROSS: {MarketRegime.RANGING, MarketRegime.TRENDING},
        }
        detector = RegimeMismatchDetector(custom_compat=custom)
        result = detector.check_mismatch(StrategyType.SMA_CROSS, MarketRegime.RANGING)
        assert result is None  # Now compatible with our custom matrix
