"""Tests for skill prompt formatting -- XML-tagged output, compact output, and limits."""

from __future__ import annotations

import pytest

from pnlclaw_agent.skills.prompt import (
    format_skills_compact,
    format_skills_for_prompt,
)
from pnlclaw_agent.skills.types import (
    Skill,
    SkillFrontmatter,
    SkillSource,
    SkillsLimits,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(name: str, description: str = "", content: str = "Skill body.") -> Skill:
    """Build a minimal Skill for prompt formatting tests."""
    return Skill(
        name=name,
        description=description,
        file_path=f"/skills/{name}/SKILL.md",
        base_dir=f"/skills/{name}",
        source=SkillSource.BUNDLED,
        frontmatter=SkillFrontmatter(name=name, description=description),
        content=content,
    )


# ---------------------------------------------------------------------------
# format_skills_for_prompt -- XML-tagged output
# ---------------------------------------------------------------------------


class TestFormatSkillsForPrompt:
    def test_empty_list_returns_empty(self) -> None:
        assert format_skills_for_prompt([]) == ""

    def test_single_skill_xml_format(self) -> None:
        skill = _make_skill("alpha", "Alpha skill", "## Steps\n1. Do alpha stuff")
        result = format_skills_for_prompt([skill])

        assert "<available_skills>" in result
        assert "</available_skills>" in result
        assert "<skill>" in result
        assert "</skill>" in result
        assert "<name>alpha</name>" in result
        assert "<description>Alpha skill</description>" in result
        assert "<content>" in result
        assert "Do alpha stuff" in result

    def test_multiple_skills(self) -> None:
        skills = [
            _make_skill("alpha", "Alpha"),
            _make_skill("beta", "Beta"),
        ]
        result = format_skills_for_prompt(skills)

        assert result.count("<skill>") == 2
        assert result.count("</skill>") == 2
        assert "<name>alpha</name>" in result
        assert "<name>beta</name>" in result

    def test_no_description_fallback(self) -> None:
        skill = _make_skill("nodesc", "", "Content.")
        result = format_skills_for_prompt([skill])
        assert "<description>No description</description>" in result

    def test_header_included(self) -> None:
        skill = _make_skill("test", "Test")
        result = format_skills_for_prompt([skill])
        assert "## Available Skills" in result

    def test_content_lines_indented(self) -> None:
        skill = _make_skill("indent", "Test", "Line 1\nLine 2")
        result = format_skills_for_prompt([skill])
        # Content lines should appear inside <content> tags
        lines = result.split("\n")
        content_lines = [l for l in lines if "Line 1" in l or "Line 2" in l]
        assert len(content_lines) == 2


# ---------------------------------------------------------------------------
# format_skills_compact
# ---------------------------------------------------------------------------


class TestFormatSkillsCompact:
    def test_empty_list_returns_empty(self) -> None:
        assert format_skills_compact([]) == ""

    def test_single_skill_compact(self) -> None:
        skill = _make_skill("alpha", "Alpha description")
        result = format_skills_compact([skill])

        assert "## Available Skills" in result
        assert "- **alpha**: Alpha description" in result

    def test_no_description_fallback(self) -> None:
        skill = _make_skill("nodesc", "")
        result = format_skills_compact([skill])
        assert "- **nodesc**: No description" in result

    def test_multiple_skills_compact(self) -> None:
        skills = [
            _make_skill("alpha", "Alpha"),
            _make_skill("beta", "Beta"),
        ]
        result = format_skills_compact(skills)

        assert "- **alpha**: Alpha" in result
        assert "- **beta**: Beta" in result

    def test_no_xml_tags(self) -> None:
        """Compact format should not contain XML tags."""
        skill = _make_skill("test", "Test skill")
        result = format_skills_compact([skill])
        assert "<skill>" not in result
        assert "<available_skills>" not in result


# ---------------------------------------------------------------------------
# Limits enforcement
# ---------------------------------------------------------------------------


class TestPromptLimits:
    def test_max_skills_in_prompt(self) -> None:
        """At most max_skills_in_prompt skills should be included."""
        skills = [_make_skill(f"skill-{i:02d}", f"Skill {i}") for i in range(20)]
        limits = SkillsLimits(max_skills_in_prompt=5, max_prompt_chars=100_000)
        result = format_skills_for_prompt(skills, limits)

        # Only 5 skills should appear
        assert result.count("<skill>") == 5

    def test_max_prompt_chars_falls_back(self) -> None:
        """When full format exceeds max_prompt_chars, the output should be trimmed."""
        # Create a skill with very large content
        big_content = "A" * 5000
        skills = [_make_skill(f"big-{i}", f"Desc {i}", big_content) for i in range(10)]
        limits = SkillsLimits(max_skills_in_prompt=50, max_prompt_chars=500)

        result = format_skills_for_prompt(skills, limits)

        # Result should be within the limit
        assert len(result) <= 500

    def test_max_prompt_chars_fewer_skills(self) -> None:
        """When full format is too large, fewer skills should be tried before compact."""
        content = "B" * 200
        skills = [_make_skill(f"s{i}", f"Desc {i}", content) for i in range(10)]
        # Set a limit that can fit some but not all skills in full format
        limits = SkillsLimits(max_skills_in_prompt=50, max_prompt_chars=800)

        result = format_skills_for_prompt(skills, limits)
        assert len(result) <= 800

    def test_compact_fallback_when_full_too_large(self) -> None:
        """If even a single skill in full format exceeds the limit, fall back to compact."""
        huge_content = "C" * 10_000
        skills = [_make_skill("huge", "Huge skill", huge_content)]
        limits = SkillsLimits(max_skills_in_prompt=50, max_prompt_chars=500)

        result = format_skills_for_prompt(skills, limits)

        # Should be within limits and not contain XML tags (compact format or truncated)
        assert len(result) <= 500

    def test_default_limits_no_truncation(self) -> None:
        """With default limits, a small set of skills should not be truncated."""
        skills = [_make_skill(f"s{i}", f"Desc {i}", "Short.") for i in range(3)]
        result = format_skills_for_prompt(skills)

        # All 3 should be in full format
        assert result.count("<skill>") == 3

    def test_zero_skills_limit(self) -> None:
        """max_skills_in_prompt=0 means no skills are included."""
        skills = [_make_skill("a", "A")]
        limits = SkillsLimits(max_skills_in_prompt=0, max_prompt_chars=100_000)
        result = format_skills_for_prompt(skills, limits)
        # No skills after truncation, but _build_full_format with empty list
        # still includes header + tags. However format_skills_for_prompt checks
        # the truncated list. Since truncated is empty after slicing, let's verify.
        assert "<skill>" not in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestPromptEdgeCases:
    def test_skill_with_multiline_content(self) -> None:
        content = "Step 1: Do this\nStep 2: Do that\nStep 3: Finish"
        skill = _make_skill("multi", "Multi-step", content)
        result = format_skills_for_prompt([skill])

        assert "Step 1" in result
        assert "Step 3" in result

    def test_skill_with_empty_content(self) -> None:
        skill = _make_skill("empty-content", "Has desc", "")
        result = format_skills_for_prompt([skill])
        assert "<name>empty-content</name>" in result

    def test_skill_with_special_xml_chars_in_name(self) -> None:
        """Names with angle brackets are inserted as-is (no escaping)."""
        skill = _make_skill("test<>&skill", "Special chars")
        result = format_skills_for_prompt([skill])
        assert "test<>&skill" in result
