"""Skills module for PnLClaw agent runtime.

Provides skill loading, registry, and prompt formatting for Markdown-based
skills (SKILL.md files with YAML frontmatter).

Public API:
    - Types: ``Skill``, ``SkillFrontmatter``, ``SkillSource``, ``SkillSummary``,
      ``SkillsConfig``, ``SkillsLimits``, ``SkillSnapshot``
    - Registry: ``SkillRegistry``
    - Formatting: ``format_skills_for_prompt``, ``format_skills_compact``
"""

from pnlclaw_agent.skills.prompt import format_skills_compact, format_skills_for_prompt
from pnlclaw_agent.skills.registry import SkillRegistry
from pnlclaw_agent.skills.types import (
    Skill,
    SkillFrontmatter,
    SkillSnapshot,
    SkillSource,
    SkillsConfig,
    SkillsLimits,
    SkillSummary,
)

__all__ = [
    "Skill",
    "SkillFrontmatter",
    "SkillRegistry",
    "SkillSnapshot",
    "SkillSource",
    "SkillsConfig",
    "SkillsLimits",
    "SkillSummary",
    "format_skills_compact",
    "format_skills_for_prompt",
]
