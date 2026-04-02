"""Skill type definitions for PnLClaw agent runtime."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SkillSource(str, Enum):
    """Where a skill was loaded from."""

    BUNDLED = "bundled"
    USER = "user"
    WORKSPACE = "workspace"
    EXTRA = "extra"


class SkillFrontmatter(BaseModel):
    """Parsed YAML frontmatter from a SKILL.md file.

    Attributes:
        name: Unique skill identifier.
        description: Short description of what the skill does.
        version: Skill version string.
        author: Skill author.
        tags: Categorization tags.
        user_invocable: Whether users can trigger via /skill_name.
        model_invocable: Whether the LLM can auto-select this skill.
        always_load: Always include in system prompt.
        requires_tools: Tool dependencies.
        requires_env: Required environment variables.
    """

    name: str = Field(..., description="Unique skill identifier")
    description: str = Field("", description="Short description of what the skill does")
    version: str = Field("0.1.0", description="Skill version")
    author: str = Field("", description="Skill author")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    user_invocable: bool = Field(True, description="Whether users can trigger via /skill_name")
    model_invocable: bool = Field(True, description="Whether the LLM can auto-select this skill")
    always_load: bool = Field(False, description="Always include in system prompt")
    requires_tools: list[str] = Field(default_factory=list, description="Tool dependencies")
    requires_env: list[str] = Field(default_factory=list, description="Required environment variables")


class Skill(BaseModel):
    """A loaded skill with parsed content.

    Attributes:
        name: Skill name from frontmatter or directory name.
        description: Skill description.
        file_path: Absolute path to SKILL.md.
        base_dir: Directory containing the SKILL.md.
        source: Where this skill was loaded from.
        frontmatter: Parsed frontmatter.
        content: Markdown body (after frontmatter).
    """

    name: str = Field(..., description="Skill name from frontmatter or directory name")
    description: str = Field("", description="Skill description")
    file_path: str = Field(..., description="Absolute path to SKILL.md")
    base_dir: str = Field(..., description="Directory containing the SKILL.md")
    source: SkillSource = Field(..., description="Where this skill was loaded from")
    frontmatter: SkillFrontmatter = Field(..., description="Parsed frontmatter")
    content: str = Field(..., description="Markdown body (after frontmatter)")


class SkillSummary(BaseModel):
    """Lightweight skill info for snapshots and API responses.

    Attributes:
        name: Skill name.
        description: Short description.
        source: Where the skill was loaded from.
        tags: Categorization tags.
        user_invocable: Whether users can trigger this skill.
        model_invocable: Whether the LLM can auto-select this skill.
    """

    name: str
    description: str
    source: SkillSource
    tags: list[str] = Field(default_factory=list)
    user_invocable: bool = True
    model_invocable: bool = True


class SkillsLimits(BaseModel):
    """Resource limits for skill loading and prompt injection.

    Attributes:
        max_skills_in_prompt: Max skills included in prompt.
        max_prompt_chars: Max characters for skills prompt block.
        max_skill_file_bytes: Max SKILL.md file size in bytes.
    """

    max_skills_in_prompt: int = Field(50, description="Max skills included in prompt")
    max_prompt_chars: int = Field(30_000, description="Max characters for skills prompt block")
    max_skill_file_bytes: int = Field(256_000, description="Max SKILL.md file size in bytes")


class SkillsConfig(BaseModel):
    """Configuration for the skills system.

    Attributes:
        extra_dirs: Additional skill directories to scan.
        enabled: Per-skill enable/disable overrides.
        limits: Resource limits for skill loading.
    """

    extra_dirs: list[str] = Field(default_factory=list, description="Additional skill directories")
    enabled: dict[str, bool] = Field(default_factory=dict, description="Per-skill enable/disable overrides")
    limits: SkillsLimits = Field(default_factory=SkillsLimits)


class SkillSnapshot(BaseModel):
    """Built skill prompt snapshot for caching.

    Attributes:
        prompt: Formatted prompt text for LLM injection.
        skills: Loaded skill summaries.
        version: Snapshot format version.
    """

    prompt: str = Field(..., description="Formatted prompt text for LLM injection")
    skills: list[SkillSummary] = Field(default_factory=list, description="Loaded skill summaries")
    version: int = Field(1, description="Snapshot format version")
