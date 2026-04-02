"""Tests for skills type models: SkillFrontmatter, Skill, SkillsConfig, SkillsLimits."""

from __future__ import annotations

import pytest

from pnlclaw_agent.skills.types import (
    Skill,
    SkillFrontmatter,
    SkillsConfig,
    SkillsLimits,
    SkillSnapshot,
    SkillSource,
    SkillSummary,
)

# ---------------------------------------------------------------------------
# SkillSource enum
# ---------------------------------------------------------------------------


class TestSkillSource:
    def test_values(self) -> None:
        assert SkillSource.BUNDLED.value == "bundled"
        assert SkillSource.USER.value == "user"
        assert SkillSource.WORKSPACE.value == "workspace"
        assert SkillSource.EXTRA.value == "extra"

    def test_all_members(self) -> None:
        members = list(SkillSource)
        assert len(members) == 4

    def test_string_comparison(self) -> None:
        assert SkillSource.BUNDLED == "bundled"
        assert SkillSource.WORKSPACE == "workspace"


# ---------------------------------------------------------------------------
# SkillFrontmatter
# ---------------------------------------------------------------------------


class TestSkillFrontmatter:
    def test_required_name(self) -> None:
        fm = SkillFrontmatter(name="my-skill")
        assert fm.name == "my-skill"

    def test_name_is_required(self) -> None:
        with pytest.raises(Exception):
            SkillFrontmatter()  # type: ignore[call-arg]

    def test_defaults(self) -> None:
        fm = SkillFrontmatter(name="test")
        assert fm.description == ""
        assert fm.version == "0.1.0"
        assert fm.author == ""
        assert fm.tags == []
        assert fm.user_invocable is True
        assert fm.model_invocable is True
        assert fm.always_load is False
        assert fm.requires_tools == []
        assert fm.requires_env == []

    def test_custom_values(self) -> None:
        fm = SkillFrontmatter(
            name="backtest-runner",
            description="Runs backtests on strategies",
            version="1.2.0",
            author="PnLClaw Team",
            tags=["backtest", "strategy"],
            user_invocable=False,
            model_invocable=True,
            always_load=True,
            requires_tools=["backtest_run", "market_history"],
            requires_env=["EXCHANGE_API_KEY"],
        )
        assert fm.name == "backtest-runner"
        assert fm.description == "Runs backtests on strategies"
        assert fm.version == "1.2.0"
        assert fm.author == "PnLClaw Team"
        assert fm.tags == ["backtest", "strategy"]
        assert fm.user_invocable is False
        assert fm.always_load is True
        assert fm.requires_tools == ["backtest_run", "market_history"]
        assert fm.requires_env == ["EXCHANGE_API_KEY"]

    def test_serialization_roundtrip(self) -> None:
        fm = SkillFrontmatter(
            name="test-skill",
            description="A test skill",
            tags=["testing"],
        )
        data = fm.model_dump()
        assert data["name"] == "test-skill"
        assert data["tags"] == ["testing"]

        restored = SkillFrontmatter.model_validate(data)
        assert restored.name == fm.name
        assert restored.description == fm.description
        assert restored.tags == fm.tags

    def test_json_roundtrip(self) -> None:
        fm = SkillFrontmatter(name="json-test", tags=["a", "b"])
        json_str = fm.model_dump_json()
        restored = SkillFrontmatter.model_validate_json(json_str)
        assert restored.name == "json-test"
        assert restored.tags == ["a", "b"]


# ---------------------------------------------------------------------------
# SkillsLimits
# ---------------------------------------------------------------------------


class TestSkillsLimits:
    def test_defaults(self) -> None:
        limits = SkillsLimits()
        assert limits.max_skills_in_prompt == 50
        assert limits.max_prompt_chars == 30_000
        assert limits.max_skill_file_bytes == 256_000

    def test_custom_values(self) -> None:
        limits = SkillsLimits(
            max_skills_in_prompt=10,
            max_prompt_chars=5000,
            max_skill_file_bytes=1024,
        )
        assert limits.max_skills_in_prompt == 10
        assert limits.max_prompt_chars == 5000
        assert limits.max_skill_file_bytes == 1024

    def test_serialization(self) -> None:
        limits = SkillsLimits(max_skills_in_prompt=25)
        data = limits.model_dump()
        assert data["max_skills_in_prompt"] == 25
        restored = SkillsLimits.model_validate(data)
        assert restored.max_skills_in_prompt == 25


# ---------------------------------------------------------------------------
# SkillsConfig
# ---------------------------------------------------------------------------


class TestSkillsConfig:
    def test_defaults(self) -> None:
        config = SkillsConfig()
        assert config.extra_dirs == []
        assert config.enabled == {}
        assert isinstance(config.limits, SkillsLimits)

    def test_custom_values(self) -> None:
        config = SkillsConfig(
            extra_dirs=["/tmp/skills", "/opt/skills"],
            enabled={"my-skill": True, "disabled-skill": False},
            limits=SkillsLimits(max_skills_in_prompt=5),
        )
        assert len(config.extra_dirs) == 2
        assert config.enabled["my-skill"] is True
        assert config.enabled["disabled-skill"] is False
        assert config.limits.max_skills_in_prompt == 5

    def test_serialization_roundtrip(self) -> None:
        config = SkillsConfig(
            extra_dirs=["/a", "/b"],
            enabled={"x": True},
        )
        data = config.model_dump()
        restored = SkillsConfig.model_validate(data)
        assert restored.extra_dirs == config.extra_dirs
        assert restored.enabled == config.enabled

    def test_nested_limits_default(self) -> None:
        config = SkillsConfig()
        assert config.limits.max_prompt_chars == 30_000


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------


class TestSkill:
    def _make_skill(self, **overrides) -> Skill:
        defaults = dict(
            name="test-skill",
            description="A test skill",
            file_path="/skills/test-skill/SKILL.md",
            base_dir="/skills/test-skill",
            source=SkillSource.BUNDLED,
            frontmatter=SkillFrontmatter(name="test-skill", description="A test skill"),
            content="## Steps\n1. Do something",
        )
        defaults.update(overrides)
        return Skill(**defaults)

    def test_basic_fields(self) -> None:
        skill = self._make_skill()
        assert skill.name == "test-skill"
        assert skill.description == "A test skill"
        assert skill.source == SkillSource.BUNDLED
        assert skill.content == "## Steps\n1. Do something"

    def test_required_fields(self) -> None:
        with pytest.raises(Exception):
            Skill()  # type: ignore[call-arg]

    def test_all_sources(self) -> None:
        for source in SkillSource:
            skill = self._make_skill(source=source)
            assert skill.source == source

    def test_serialization_roundtrip(self) -> None:
        skill = self._make_skill()
        data = skill.model_dump()
        assert data["name"] == "test-skill"
        assert data["source"] == "bundled"

        restored = Skill.model_validate(data)
        assert restored.name == skill.name
        assert restored.frontmatter.name == skill.frontmatter.name

    def test_json_roundtrip(self) -> None:
        skill = self._make_skill()
        json_str = skill.model_dump_json()
        restored = Skill.model_validate_json(json_str)
        assert restored.name == "test-skill"
        assert restored.source == SkillSource.BUNDLED


# ---------------------------------------------------------------------------
# SkillSummary
# ---------------------------------------------------------------------------


class TestSkillSummary:
    def test_basic(self) -> None:
        summary = SkillSummary(
            name="my-skill",
            description="Does things",
            source=SkillSource.USER,
        )
        assert summary.name == "my-skill"
        assert summary.description == "Does things"
        assert summary.source == SkillSource.USER
        assert summary.tags == []
        assert summary.user_invocable is True
        assert summary.model_invocable is True

    def test_custom_flags(self) -> None:
        summary = SkillSummary(
            name="x",
            description="x",
            source=SkillSource.WORKSPACE,
            tags=["alpha"],
            user_invocable=False,
            model_invocable=False,
        )
        assert summary.user_invocable is False
        assert summary.model_invocable is False
        assert summary.tags == ["alpha"]


# ---------------------------------------------------------------------------
# SkillSnapshot
# ---------------------------------------------------------------------------


class TestSkillSnapshot:
    def test_basic(self) -> None:
        snap = SkillSnapshot(prompt="## Skills\n...", skills=[], version=1)
        assert snap.prompt == "## Skills\n..."
        assert snap.skills == []
        assert snap.version == 1

    def test_with_summaries(self) -> None:
        summaries = [
            SkillSummary(name="a", description="A skill", source=SkillSource.BUNDLED),
            SkillSummary(name="b", description="B skill", source=SkillSource.USER),
        ]
        snap = SkillSnapshot(prompt="prompt text", skills=summaries)
        assert len(snap.skills) == 2
        assert snap.skills[0].name == "a"

    def test_serialization(self) -> None:
        snap = SkillSnapshot(prompt="test", skills=[])
        data = snap.model_dump()
        restored = SkillSnapshot.model_validate(data)
        assert restored.prompt == "test"
        assert restored.version == 1
