"""Tests for SkillLoader -- SKILL.md parsing, directory scanning, and safety guards."""

from __future__ import annotations

from pathlib import Path

import pytest

from pnlclaw_agent.skills.loader import SkillLoader, _parse_frontmatter
from pnlclaw_agent.skills.types import SkillsLimits, SkillSource

# ---------------------------------------------------------------------------
# _parse_frontmatter unit tests
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_valid_frontmatter(self) -> None:
        raw = "---\nname: my-skill\ndescription: Does stuff\n---\nBody content here."
        data, body = _parse_frontmatter(raw)
        assert data["name"] == "my-skill"
        assert data["description"] == "Does stuff"
        assert body == "Body content here."

    def test_no_frontmatter(self) -> None:
        raw = "# Just markdown\n\nNo frontmatter here."
        data, body = _parse_frontmatter(raw)
        assert data == {}
        assert body == raw

    def test_only_one_delimiter(self) -> None:
        raw = "---\nname: broken\nNo closing delimiter."
        data, body = _parse_frontmatter(raw)
        assert data == {}
        # Returns full text as body when there is no valid frontmatter
        assert "broken" in body

    def test_bom_stripped(self) -> None:
        raw = "\ufeff---\nname: bom-skill\n---\nContent."
        data, body = _parse_frontmatter(raw)
        assert data["name"] == "bom-skill"
        assert body == "Content."

    def test_invalid_yaml(self) -> None:
        raw = "---\n: : : bad yaml\n---\nBody."
        data, body = _parse_frontmatter(raw)
        # Invalid YAML returns empty dict and full text
        assert data == {}

    def test_yaml_returns_non_dict(self) -> None:
        raw = "---\n- just a list\n---\nBody."
        data, body = _parse_frontmatter(raw)
        assert data == {}

    def test_multiline_body(self) -> None:
        raw = "---\nname: test\n---\nLine one.\nLine two.\nLine three."
        data, body = _parse_frontmatter(raw)
        assert data["name"] == "test"
        assert "Line one." in body
        assert "Line three." in body

    def test_complex_frontmatter(self) -> None:
        raw = "---\nname: complex\ntags:\n  - alpha\n  - beta\nrequires_tools:\n  - market_ticker\n---\nBody here."
        data, body = _parse_frontmatter(raw)
        assert data["name"] == "complex"
        assert data["tags"] == ["alpha", "beta"]
        assert data["requires_tools"] == ["market_ticker"]


# ---------------------------------------------------------------------------
# SkillLoader -- directory scanning
# ---------------------------------------------------------------------------


class TestSkillLoaderScan:
    def test_load_single_skill(self, tmp_path: Path) -> None:
        """A directory with one valid SKILL.md should yield one Skill."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\nname: my-skill\ndescription: Test skill\n---\n## Steps\n1. Do stuff",
            encoding="utf-8",
        )

        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        skills = loader.scan()

        assert len(skills) == 1
        assert skills[0].name == "my-skill"
        assert skills[0].description == "Test skill"
        assert skills[0].source == SkillSource.BUNDLED
        assert "Do stuff" in skills[0].content

    def test_load_multiple_skills(self, tmp_path: Path) -> None:
        """Multiple skill subdirectories should all be loaded and sorted by name."""
        for name in ["zebra", "alpha", "middle"]:
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {name} skill\n---\nContent.",
                encoding="utf-8",
            )

        loader = SkillLoader(tmp_path, SkillSource.USER)
        skills = loader.scan()

        assert len(skills) == 3
        names = [s.name for s in skills]
        assert names == ["alpha", "middle", "zebra"]

    def test_no_skill_md_skipped(self, tmp_path: Path) -> None:
        """Subdirectories without SKILL.md should be silently skipped."""
        (tmp_path / "has-skill").mkdir()
        (tmp_path / "has-skill" / "SKILL.md").write_text("---\nname: has-skill\n---\nBody.", encoding="utf-8")
        (tmp_path / "no-skill").mkdir()
        (tmp_path / "no-skill" / "README.md").write_text("Not a skill.", encoding="utf-8")

        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        skills = loader.scan()
        assert len(skills) == 1
        assert skills[0].name == "has-skill"

    def test_nonexistent_root_dir(self, tmp_path: Path) -> None:
        """A nonexistent root returns an empty list."""
        loader = SkillLoader(tmp_path / "does-not-exist", SkillSource.BUNDLED)
        assert loader.scan() == []

    def test_empty_root_dir(self, tmp_path: Path) -> None:
        """An empty root directory returns an empty list."""
        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        assert loader.scan() == []

    def test_files_at_root_ignored(self, tmp_path: Path) -> None:
        """Files directly in root (not subdirectories) are ignored."""
        (tmp_path / "SKILL.md").write_text("---\nname: root\n---\nBody.", encoding="utf-8")
        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        assert loader.scan() == []


# ---------------------------------------------------------------------------
# SkillLoader -- frontmatter fallback
# ---------------------------------------------------------------------------


class TestSkillLoaderFallback:
    def test_no_frontmatter_uses_dir_name(self, tmp_path: Path) -> None:
        """SKILL.md without frontmatter should use directory name as skill name."""
        skill_dir = tmp_path / "fallback-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# No frontmatter\nJust plain markdown body.", encoding="utf-8")

        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        skills = loader.scan()

        assert len(skills) == 1
        assert skills[0].name == "fallback-skill"

    def test_frontmatter_without_name_uses_dir_name(self, tmp_path: Path) -> None:
        """Frontmatter missing the name field should fall back to directory name."""
        skill_dir = tmp_path / "dir-named"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: Has desc but no name\n---\nBody.", encoding="utf-8")

        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        skills = loader.scan()

        assert len(skills) == 1
        assert skills[0].name == "dir-named"
        assert skills[0].description == "Has desc but no name"


# ---------------------------------------------------------------------------
# SkillLoader -- file size limits
# ---------------------------------------------------------------------------


class TestSkillLoaderFileSizeLimit:
    def test_file_within_limit_loads(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "small"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: small\n---\nSmall body.", encoding="utf-8")

        limits = SkillsLimits(max_skill_file_bytes=10_000)
        loader = SkillLoader(tmp_path, SkillSource.BUNDLED, limits)
        skills = loader.scan()
        assert len(skills) == 1

    def test_file_exceeding_limit_skipped(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "large"
        skill_dir.mkdir()
        # Write a file larger than the limit
        content = "---\nname: large\n---\n" + "x" * 500
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

        limits = SkillsLimits(max_skill_file_bytes=100)
        loader = SkillLoader(tmp_path, SkillSource.BUNDLED, limits)
        skills = loader.scan()
        assert len(skills) == 0

    def test_exact_limit_loads(self, tmp_path: Path) -> None:
        """A file exactly at the limit should be loaded."""
        skill_dir = tmp_path / "exact"
        skill_dir.mkdir()
        # Write frontmatter + body to hit exact limit
        content = "---\nname: exact\n---\nBody."
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        file_size = (skill_dir / "SKILL.md").stat().st_size

        limits = SkillsLimits(max_skill_file_bytes=file_size)
        loader = SkillLoader(tmp_path, SkillSource.BUNDLED, limits)
        skills = loader.scan()
        assert len(skills) == 1


# ---------------------------------------------------------------------------
# SkillLoader -- path traversal protection
# ---------------------------------------------------------------------------


class TestSkillLoaderPathTraversal:
    def test_symlink_outside_root_blocked(self, tmp_path: Path) -> None:
        """Symlinks that resolve outside the root directory should be blocked."""
        # Create an outside directory with a valid SKILL.md
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        (outside_dir / "SKILL.md").write_text("---\nname: evil\n---\nMalicious content.", encoding="utf-8")

        # Create the root skills directory
        skills_root = tmp_path / "skills"
        skills_root.mkdir()

        # Create a symlink inside root that points outside
        link_path = skills_root / "evil-link"
        try:
            link_path.symlink_to(outside_dir)
        except OSError:
            pytest.skip("Cannot create symlinks on this system")

        loader = SkillLoader(skills_root, SkillSource.BUNDLED)
        skills = loader.scan()

        # The symlinked skill should not be loaded because it resolves outside root
        evil_names = [s.name for s in skills if s.name == "evil"]
        assert len(evil_names) == 0

    def test_normal_subdirectory_allowed(self, tmp_path: Path) -> None:
        """Normal subdirectories within the root should load fine."""
        skill_dir = tmp_path / "safe-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: safe\n---\nSafe content.", encoding="utf-8")

        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        skills = loader.scan()
        assert len(skills) == 1
        assert skills[0].name == "safe"


# ---------------------------------------------------------------------------
# SkillLoader -- invalid YAML handling
# ---------------------------------------------------------------------------


class TestSkillLoaderInvalidYaml:
    def test_invalid_yaml_graceful(self, tmp_path: Path) -> None:
        """Invalid YAML frontmatter should not crash the loader."""
        skill_dir = tmp_path / "bad-yaml"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\n: : : garbage\n---\nBody content.", encoding="utf-8")

        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        skills = loader.scan()
        # Invalid YAML means the skill cannot be parsed, so it falls back
        # to treating the whole file as body. The dir name becomes the name.
        # Depending on how _parse_frontmatter fails, it may still load.
        # The key is it does not crash.
        assert isinstance(skills, list)

    def test_frontmatter_invalid_types(self, tmp_path: Path) -> None:
        """Frontmatter with invalid field types should skip the skill gracefully."""
        skill_dir = tmp_path / "bad-types"
        skill_dir.mkdir()
        # tags should be a list, not a string -- depending on Pydantic coercion
        # this may or may not fail, but must not crash
        (skill_dir / "SKILL.md").write_text("---\nname: bad\ntags: not-a-list\n---\nBody.", encoding="utf-8")

        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        skills = loader.scan()
        assert isinstance(skills, list)


# ---------------------------------------------------------------------------
# SkillLoader -- load_single
# ---------------------------------------------------------------------------


class TestSkillLoaderSingle:
    def test_load_single_valid(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "single"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: single\n---\nContent.", encoding="utf-8")

        loader = SkillLoader(tmp_path, SkillSource.WORKSPACE)
        skill = loader.load_single(skill_dir)

        assert skill is not None
        assert skill.name == "single"
        assert skill.source == SkillSource.WORKSPACE

    def test_load_single_no_file(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "empty"
        skill_dir.mkdir()

        loader = SkillLoader(tmp_path, SkillSource.WORKSPACE)
        skill = loader.load_single(skill_dir)
        assert skill is None

    def test_load_single_nonexistent_dir(self, tmp_path: Path) -> None:
        loader = SkillLoader(tmp_path, SkillSource.WORKSPACE)
        skill = loader.load_single(tmp_path / "does-not-exist")
        assert skill is None

    def test_content_stripped(self, tmp_path: Path) -> None:
        """Body content should have leading/trailing whitespace stripped."""
        skill_dir = tmp_path / "strip"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: strip\n---\n\n  Content here  \n\n", encoding="utf-8")

        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        skill = loader.load_single(skill_dir)
        assert skill is not None
        assert skill.content == "Content here"


# ---------------------------------------------------------------------------
# SkillLoader -- properties
# ---------------------------------------------------------------------------


class TestSkillLoaderProperties:
    def test_root_dir(self, tmp_path: Path) -> None:
        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        assert loader.root_dir == tmp_path.resolve()

    def test_source(self, tmp_path: Path) -> None:
        loader = SkillLoader(tmp_path, SkillSource.USER)
        assert loader.source == SkillSource.USER

    def test_default_limits(self, tmp_path: Path) -> None:
        loader = SkillLoader(tmp_path, SkillSource.BUNDLED)
        # The default limits should be the SkillsLimits defaults
        # Access via scan() to confirm no crash
        assert loader.scan() == []
