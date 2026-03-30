"""Tests for financial hallucination detection (v0.1.1).

Sprint 2.1 — Validates unverified claim scanning, investment promise
detection, secret redaction, and golden response snapshots.
"""

from __future__ import annotations

import pytest

from pnlclaw_security.guardrails.hallucination import HallucinationDetector, ScanResult

# ---------------------------------------------------------------------------
# Test 1: Unverified price claim → appends warning
# ---------------------------------------------------------------------------


class TestUnverifiedClaims:
    def test_price_without_tool_support_triggers_warning(self) -> None:
        detector = HallucinationDetector()
        result = detector.scan_text_for_unverified_claims(
            "BTC is currently at $100,000 and ETH at $5,000.",
            tool_results=[],
        )
        assert result.triggered is True
        assert any("未经工具验证" in w for w in result.warnings)

    def test_multiple_unsupported_claims(self) -> None:
        detector = HallucinationDetector()
        result = detector.scan_text_for_unverified_claims(
            "The Sharpe ratio is 2.5 and drawdown is 15%.",
            tool_results=[],
        )
        assert result.triggered is True
        assert len(result.warnings) >= 1


# ---------------------------------------------------------------------------
# Test 2: Verified price claim → no warning
# ---------------------------------------------------------------------------


class TestVerifiedClaims:
    def test_price_with_tool_support_no_warning(self) -> None:
        detector = HallucinationDetector()
        result = detector.scan_text_for_unverified_claims(
            "BTC is currently at $67,234.",
            tool_results=[{"output": "BTC/USDT price: 67234.0", "tool": "market_ticker"}],
        )
        assert result.triggered is False
        assert len(result.warnings) == 0

    def test_percentage_with_tool_support_no_warning(self) -> None:
        detector = HallucinationDetector()
        result = detector.scan_text_for_unverified_claims(
            "Strategy returned 23.5% annualized.",
            tool_results=[{"output": "Return: 23.5% annualized", "tool": "backtest_run"}],
        )
        assert result.triggered is False


# ---------------------------------------------------------------------------
# Test 3: Investment promise detection
# ---------------------------------------------------------------------------


class TestInvestmentPromises:
    @pytest.mark.parametrize(
        "text",
        [
            "这个策略保证盈利",
            "这是一个零风险的投资",
            "买这个必涨",
            "This strategy has guaranteed returns",
            "Risk-free opportunity",
            "You can't lose with this approach",
            "Sure profit strategy",
            "稳赚不赔",
        ],
    )
    def test_promise_triggers_disclaimer(self, text: str) -> None:
        detector = HallucinationDetector()
        result = detector.scan_for_investment_promises(text)
        assert result.triggered is True
        assert any("投资有风险" in w for w in result.warnings)

    def test_normal_text_no_promise(self) -> None:
        detector = HallucinationDetector()
        result = detector.scan_for_investment_promises(
            "Based on historical data, this strategy shows a Sharpe ratio of 1.5."
        )
        assert result.triggered is False
        assert len(result.warnings) == 0


# ---------------------------------------------------------------------------
# Test 4: Secret redaction in output
# ---------------------------------------------------------------------------


class TestSecretRedaction:
    def test_api_key_redacted(self) -> None:
        detector = HallucinationDetector()
        text = "Your API key is sk-abc123456789012345678"
        redacted = detector.redact_secrets_in_output(text)
        assert "sk-abc123456789012345678" not in redacted

    def test_bearer_token_redacted(self) -> None:
        detector = HallucinationDetector()
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        redacted = detector.redact_secrets_in_output(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted

    def test_clean_text_unchanged(self) -> None:
        detector = HallucinationDetector()
        text = "BTC price is $67,234. No secrets here."
        redacted = detector.redact_secrets_in_output(text)
        assert redacted == text


# ---------------------------------------------------------------------------
# Test 5: Golden Response snapshot (regression guard)
# ---------------------------------------------------------------------------


class TestGoldenResponseSnapshot:
    """Fixed input/output snapshot to detect prompt or detection logic drift."""

    GOLDEN_INPUT = "BTC 当前 $100,000，这个策略保证盈利，API key: sk-test1234567890abcdef"
    GOLDEN_TOOL_RESULTS: list[dict] = []

    def test_golden_response_snapshot(self) -> None:
        detector = HallucinationDetector()
        text, scan_result = detector.scan_output(
            self.GOLDEN_INPUT,
            tool_results=self.GOLDEN_TOOL_RESULTS,
        )

        # Secret must be redacted
        assert "sk-test1234567890abcdef" not in text

        # Investment promise disclaimer must be present
        assert "投资有风险" in text

        # Unverified claim warnings are logged internally only, not in output
        assert "未经工具验证" not in text

        # Overall scan should have triggered (internally)
        assert scan_result.triggered is True


# ---------------------------------------------------------------------------
# Test 6: Property test — output never contains unredacted secret
# ---------------------------------------------------------------------------


class TestSecretPropertyTest:
    @pytest.mark.parametrize(
        "secret",
        [
            "sk-abcdef1234567890abcdef",
            "ghp_abcdef1234567890abcdef1234567890",
            "AKIA1234567890123456",
        ],
    )
    def test_output_never_contains_unredacted_secret(self, secret: str) -> None:
        detector = HallucinationDetector()
        text = f"Here is a result. The key is {secret}. Thanks!"
        redacted = detector.redact_secrets_in_output(text)
        assert secret not in redacted


# ---------------------------------------------------------------------------
# Test 7: scan_output integration
# ---------------------------------------------------------------------------


class TestScanOutputIntegration:
    def test_scan_output_combines_all_checks(self) -> None:
        detector = HallucinationDetector()
        text = "BTC is $99,999. This strategy guarantees profit."
        result_text, scan = detector.scan_output(text, tool_results=[])

        assert scan.triggered is True
        # Unverified claims are logged internally, not shown to users
        assert "未经工具验证" not in result_text
        # Investment promise disclaimer IS shown to users
        assert "投资有风险" in result_text

    def test_scan_output_clean_text_passes(self) -> None:
        detector = HallucinationDetector()
        text = "Based on the data retrieved, the analysis shows mixed signals."
        result_text, scan = detector.scan_output(text, tool_results=[])

        assert scan.triggered is False
        assert result_text == text
