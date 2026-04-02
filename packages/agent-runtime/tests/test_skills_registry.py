"""Tests for SkillRegistry -- multi-source loading, priority merging, and filtering."""

from __future__ import annotations

from pathlib import Path

from pnlclaw_agent.skills.registry import SkillRegistry
from pnlclaw_agent.skills.types import SkillsConfig, SkillSource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_skill_dir(root: Path, name: str, description: str = "") -> Path:
    """Create a skill subdirectory with a SKILL.md file."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    desc_line = f"description: {description}\n" if description else ""
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\n{desc_line}---\nContent for {name}.",
        encoding="utf-8",
    )
    return skill_dir


def _create_skill_with_tools(root: Path, name: str, requires_tools: list[str]) -> Path:
    """Create a skill subdirectory with tool requirements in frontmatter."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    tools_yaml = "\n".join(f"  - {t}" for t in requires_tools)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\nrequires_tools:\n{tools_yaml}\n---\nContent.",
        encoding="utf-8",
    )
    return skill_dir


# ---------------------------------------------------------------------------
# Basic loading
# ---------------------------------------------------------------------------


class TestSkillRegistryLoading:
    def test_load_from_bundled_dir(self, tmp_path: Path) -> None:
        """Skills in the bundled directory should be loaded."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "alpha", "Alpha skill")
        _create_skill_dir(bundled, "beta", "Beta skill")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "empty-user")
        registry.load()

        assert registry.is_loaded
        assert len(registry) == 2
        assert "alpha" in registry
        assert "beta" in registry

    def test_lazy_load_on_get(self, tmp_path: Path) -> None:
        """get() should trigger load if not yet loaded."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "lazy")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")
        assert not registry.is_loaded

        skill = registry.get("lazy")
        assert registry.is_loaded
        assert skill is not None
        assert skill.name == "lazy"

    def test_get_nonexistent(self, tmp_path: Path) -> None:
        """get() for a nonexistent skill returns None."""
        registry = SkillRegistry(bundled_dir=tmp_path / "empty", user_dir=tmp_path / "eu")
        assert registry.get("does-not-exist") is None

    def test_empty_dirs(self, tmp_path: Path) -> None:
        """No skills should be loaded when all source directories are empty."""
        registry = SkillRegistry(
            bundled_dir=tmp_path / "b",
            user_dir=tmp_path / "u",
            workspace_dir=tmp_path / "w",
        )
        registry.load()
        assert len(registry) == 0
        assert registry.list_skills() == []


# ---------------------------------------------------------------------------
# Priority merging
# ---------------------------------------------------------------------------


class TestSkillRegistryPriority:
    def test_workspace_overrides_bundled(self, tmp_path: Path) -> None:
        """Workspace skills should override bundled skills with the same name."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "shared", "Bundled version")

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _create_skill_dir(workspace, "shared", "Workspace version")

        registry = SkillRegistry(
            bundled_dir=bundled,
            user_dir=tmp_path / "eu",
            workspace_dir=workspace,
        )
        registry.load()

        skill = registry.get("shared")
        assert skill is not None
        assert skill.source == SkillSource.WORKSPACE
        assert skill.description == "Workspace version"

    def test_user_overrides_bundled(self, tmp_path: Path) -> None:
        """User skills override bundled skills with the same name."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "common", "Bundled version")

        user = tmp_path / "user"
        user.mkdir()
        _create_skill_dir(user, "common", "User version")

        registry = SkillRegistry(
            bundled_dir=bundled,
            user_dir=user,
        )
        registry.load()

        skill = registry.get("common")
        assert skill is not None
        assert skill.source == SkillSource.USER
        assert skill.description == "User version"

    def test_workspace_overrides_user(self, tmp_path: Path) -> None:
        """Workspace is highest priority, overriding even user skills."""
        user = tmp_path / "user"
        user.mkdir()
        _create_skill_dir(user, "priority", "User version")

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _create_skill_dir(workspace, "priority", "Workspace version")

        registry = SkillRegistry(
            bundled_dir=tmp_path / "empty",
            user_dir=user,
            workspace_dir=workspace,
        )
        registry.load()

        skill = registry.get("priority")
        assert skill is not None
        assert skill.source == SkillSource.WORKSPACE

    def test_extra_dir_lowest_priority(self, tmp_path: Path) -> None:
        """Extra dirs have lowest priority and are overridden by bundled."""
        extra = tmp_path / "extra"
        extra.mkdir()
        _create_skill_dir(extra, "override-me", "Extra version")

        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "override-me", "Bundled version")

        config = SkillsConfig(extra_dirs=[str(extra)])
        registry = SkillRegistry(
            config=config,
            bundled_dir=bundled,
            user_dir=tmp_path / "eu",
        )
        registry.load()

        skill = registry.get("override-me")
        assert skill is not None
        assert skill.source == SkillSource.BUNDLED

    def test_non_overlapping_skills_all_loaded(self, tmp_path: Path) -> None:
        """Non-overlapping skills from different sources should all be present."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "bundled-only")

        user = tmp_path / "user"
        user.mkdir()
        _create_skill_dir(user, "user-only")

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _create_skill_dir(workspace, "workspace-only")

        registry = SkillRegistry(
            bundled_dir=bundled,
            user_dir=user,
            workspace_dir=workspace,
        )
        registry.load()

        assert len(registry) == 3
        assert "bundled-only" in registry
        assert "user-only" in registry
        assert "workspace-only" in registry


# ---------------------------------------------------------------------------
# list_skills and list_summaries
# ---------------------------------------------------------------------------


class TestSkillRegistryListing:
    def test_list_skills_sorted(self, tmp_path: Path) -> None:
        """list_skills() returns skills sorted by name."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "zebra")
        _create_skill_dir(bundled, "alpha")
        _create_skill_dir(bundled, "mid")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")
        skills = registry.list_skills()

        names = [s.name for s in skills]
        assert names == ["alpha", "mid", "zebra"]

    def test_list_summaries(self, tmp_path: Path) -> None:
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "sum-test", "Summary test skill")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")
        summaries = registry.list_summaries()

        assert len(summaries) == 1
        assert summaries[0].name == "sum-test"
        assert summaries[0].description == "Summary test skill"
        assert summaries[0].source == SkillSource.BUNDLED

    def test_skill_names(self, tmp_path: Path) -> None:
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "b-skill")
        _create_skill_dir(bundled, "a-skill")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")
        names = registry.skill_names()
        assert names == ["a-skill", "b-skill"]


# ---------------------------------------------------------------------------
# list_eligible with tool filtering
# ---------------------------------------------------------------------------


class TestSkillRegistryEligible:
    def test_all_eligible_when_no_tool_filter(self, tmp_path: Path) -> None:
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_with_tools(bundled, "needs-tools", ["market_ticker"])
        _create_skill_dir(bundled, "no-tools")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")
        eligible = registry.list_eligible(available_tools=None)
        assert len(eligible) == 2

    def test_eligible_with_tool_check(self, tmp_path: Path) -> None:
        """Skills with satisfied tool requirements are eligible."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_with_tools(bundled, "needs-ticker", ["market_ticker"])
        _create_skill_with_tools(bundled, "needs-backtest", ["backtest_run"])
        _create_skill_dir(bundled, "no-requirements")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")
        eligible = registry.list_eligible(available_tools=["market_ticker"])

        names = [s.name for s in eligible]
        assert "needs-ticker" in names
        assert "no-requirements" in names
        assert "needs-backtest" not in names

    def test_eligible_all_tools_required(self, tmp_path: Path) -> None:
        """A skill requiring multiple tools is only eligible if ALL are available."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_with_tools(bundled, "multi-tool", ["tool_a", "tool_b"])

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")

        # Only one tool available -- should not be eligible
        eligible = registry.list_eligible(available_tools=["tool_a"])
        assert len(eligible) == 0

        # Both tools available
        eligible = registry.list_eligible(available_tools=["tool_a", "tool_b"])
        assert len(eligible) == 1
        assert eligible[0].name == "multi-tool"

    def test_eligible_empty_tools_list(self, tmp_path: Path) -> None:
        """An empty tools list means no tools are available."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_with_tools(bundled, "needs-tool", ["market_ticker"])
        _create_skill_dir(bundled, "no-tools")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")
        eligible = registry.list_eligible(available_tools=[])

        assert len(eligible) == 1
        assert eligible[0].name == "no-tools"


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


class TestSkillRegistryRefresh:
    def test_refresh_reloads(self, tmp_path: Path) -> None:
        """refresh() should reload skills, picking up new ones."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "original")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")
        registry.load()
        assert len(registry) == 1

        # Add a new skill
        _create_skill_dir(bundled, "new-skill")
        registry.refresh()

        assert len(registry) == 2
        assert "new-skill" in registry

    def test_refresh_picks_up_removals(self, tmp_path: Path) -> None:
        """refresh() should reflect removed skills."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        skill_dir = _create_skill_dir(bundled, "to-remove")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")
        registry.load()
        assert "to-remove" in registry

        # Remove the skill directory
        import shutil

        shutil.rmtree(skill_dir)
        registry.refresh()

        assert "to-remove" not in registry


# ---------------------------------------------------------------------------
# Enabled/disabled config
# ---------------------------------------------------------------------------


class TestSkillRegistryEnabledConfig:
    def test_disabled_skill_excluded(self, tmp_path: Path) -> None:
        """A skill explicitly disabled in config should not be loaded."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "enabled-skill")
        _create_skill_dir(bundled, "disabled-skill")

        config = SkillsConfig(enabled={"disabled-skill": False})
        registry = SkillRegistry(config=config, bundled_dir=bundled, user_dir=tmp_path / "eu")
        registry.load()

        assert "enabled-skill" in registry
        assert "disabled-skill" not in registry
        assert len(registry) == 1

    def test_explicitly_enabled_skill_loaded(self, tmp_path: Path) -> None:
        """A skill explicitly enabled in config should be loaded."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "explicit")

        config = SkillsConfig(enabled={"explicit": True})
        registry = SkillRegistry(config=config, bundled_dir=bundled, user_dir=tmp_path / "eu")
        registry.load()

        assert "explicit" in registry

    def test_skills_not_in_config_default_enabled(self, tmp_path: Path) -> None:
        """Skills not mentioned in the enabled dict are loaded by default."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "unlisted")

        config = SkillsConfig(enabled={"other": False})
        registry = SkillRegistry(config=config, bundled_dir=bundled, user_dir=tmp_path / "eu")
        registry.load()

        assert "unlisted" in registry


# ---------------------------------------------------------------------------
# contains and len
# ---------------------------------------------------------------------------


class TestSkillRegistryDunderMethods:
    def test_contains(self, tmp_path: Path) -> None:
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "exists")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")
        assert "exists" in registry
        assert "nonexistent" not in registry

    def test_len(self, tmp_path: Path) -> None:
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        _create_skill_dir(bundled, "one")
        _create_skill_dir(bundled, "two")

        registry = SkillRegistry(bundled_dir=bundled, user_dir=tmp_path / "eu")
        assert len(registry) == 2
