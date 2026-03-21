"""Tests for pnlclaw_types.risk — serialization/deserialization roundtrips."""

from pnlclaw_types.risk import RiskAlert, RiskDecision, RiskLevel, RiskRule


class TestRiskLevel:
    def test_four_levels(self):
        """Spec: RiskLevel must have exactly safe/restricted/dangerous/blocked."""
        expected = {"safe", "restricted", "dangerous", "blocked"}
        actual = {level.value for level in RiskLevel}
        assert actual == expected


class TestRiskRule:
    def test_roundtrip(self):
        r = RiskRule(
            id="rule-max-pos",
            name="Max Position Size",
            description="Limits single position to 10%",
            level=RiskLevel.RESTRICTED,
            parameters={"max_position_pct": 0.1},
            enabled=True,
        )
        raw = r.model_dump_json()
        restored = RiskRule.model_validate_json(raw)
        assert restored == r

    def test_defaults(self):
        r = RiskRule(id="rule-001", name="Test", level=RiskLevel.SAFE)
        assert r.enabled is True
        assert r.parameters == {}
        assert r.description == ""


class TestRiskDecision:
    def test_roundtrip(self):
        d = RiskDecision(
            rule_id="rule-max-pos",
            allowed=False,
            level=RiskLevel.RESTRICTED,
            reason="Position too large",
            timestamp=1711000000000,
        )
        raw = d.model_dump_json()
        restored = RiskDecision.model_validate_json(raw)
        assert restored == d
        assert restored.allowed is False


class TestRiskAlert:
    def test_roundtrip(self):
        a = RiskAlert(
            id="alert-001",
            rule_id="rule-max-pos",
            level=RiskLevel.DANGEROUS,
            message="Daily loss limit breached",
            context={"daily_loss": -500.0},
            timestamp=1711000000000,
        )
        raw = a.model_dump_json()
        restored = RiskAlert.model_validate_json(raw)
        assert restored == a
        assert restored.acknowledged is False

    def test_acknowledged(self):
        a = RiskAlert(
            id="alert-002",
            rule_id="rule-001",
            level=RiskLevel.SAFE,
            message="Info",
            timestamp=1711000000000,
            acknowledged=True,
        )
        assert a.acknowledged is True
