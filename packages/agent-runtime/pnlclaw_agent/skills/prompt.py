"""Skill prompt formatting -- builds LLM-injectable prompt blocks from skills.

Provides two formatting modes:
- Full format with XML-like tags and complete skill content.
- Compact format with name and description only (used as fallback).
"""

from __future__ import annotations

from pnlclaw_agent.skills.types import Skill, SkillsLimits

_SKILLS_HEADER = """\
## Available Skills
The following skills provide specialized workflows for quantitative trading tasks.
When the user's request matches a skill, follow its steps and use the specified tools."""


def format_skills_for_prompt(
    skills: list[Skill],
    limits: SkillsLimits | None = None,
) -> str:
    """Format skills as a full prompt block with XML-like tags.

    Each skill's complete markdown content is included inside ``<skill>``
    tags.  If the resulting prompt exceeds ``limits.max_prompt_chars``,
    the function falls back to compact format.  At most
    ``limits.max_skills_in_prompt`` skills are included.

    Args:
        skills: List of skills to format.
        limits: Resource limits for prompt size enforcement.

    Returns:
        Formatted prompt string ready for system prompt injection.
    """
    if not skills:
        return ""

    limits = limits or SkillsLimits()

    # Enforce max skill count
    truncated = skills[: limits.max_skills_in_prompt]

    # Build full format
    full_prompt = _build_full_format(truncated)

    # If full format is within limits, use it
    if len(full_prompt) <= limits.max_prompt_chars:
        return full_prompt

    # Try with fewer skills until it fits or give up
    for count in range(len(truncated) - 1, 0, -1):
        candidate = _build_full_format(truncated[:count])
        if len(candidate) <= limits.max_prompt_chars:
            return candidate

    # Fall back to compact format
    compact = format_skills_compact(truncated)
    if len(compact) <= limits.max_prompt_chars:
        return compact

    # Even compact is too large, truncate to limit
    return compact[: limits.max_prompt_chars]


def format_skills_compact(skills: list[Skill]) -> str:
    """Format skills in a compact list (name + description only).

    This is used as a fallback when full format exceeds prompt limits.

    Args:
        skills: List of skills to format.

    Returns:
        Compact prompt string with skill names and descriptions.
    """
    if not skills:
        return ""

    lines = [_SKILLS_HEADER, ""]
    for skill in skills:
        desc = skill.description or "No description"
        lines.append(f"- **{skill.name}**: {desc}")

    return "\n".join(lines)


def _build_full_format(skills: list[Skill]) -> str:
    """Build the full XML-tagged format for the given skills.

    Args:
        skills: List of skills to format.

    Returns:
        Full format prompt string.
    """
    parts = [_SKILLS_HEADER, "", "<available_skills>"]

    for skill in skills:
        parts.append("  <skill>")
        parts.append(f"    <name>{skill.name}</name>")
        desc = skill.description or "No description"
        parts.append(f"    <description>{desc}</description>")
        parts.append("    <content>")
        # Indent content lines for readability
        for line in skill.content.splitlines():
            parts.append(f"    {line}")
        parts.append("    </content>")
        parts.append("  </skill>")

    parts.append("</available_skills>")

    return "\n".join(parts)
