"""Skill registry -- aggregates skills from multiple sources with priority.

The registry loads skills from bundled, user, workspace, and extra directories,
deduplicates by name with source priority, and provides lookup/filtering APIs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pnlclaw_agent.skills.loader import SkillLoader
from pnlclaw_agent.skills.types import (
    Skill,
    SkillsConfig,
    SkillSource,
    SkillSummary,
)

try:
    import structlog

    logger: Any = structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

# Source priority: higher number wins when names collide.
_SOURCE_PRIORITY: dict[SkillSource, int] = {
    SkillSource.EXTRA: 0,
    SkillSource.BUNDLED: 1,
    SkillSource.USER: 2,
    SkillSource.WORKSPACE: 3,
}


def _default_bundled_dir() -> Path:
    """Return the default bundled skills directory (project root ``skills/``).

    Walks up from this file to find the project root containing a
    ``pyproject.toml`` or ``skills/`` directory.
    """
    # Start from this file's location and walk up
    current = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = current / "skills"
        if candidate.is_dir():
            return candidate
        if (current / "pyproject.toml").is_file():
            # We're at project root but skills/ doesn't exist yet
            return current / "skills"
        parent = current.parent
        if parent == current:
            break
        current = parent
    # Fallback: assume skills/ at CWD
    return Path.cwd() / "skills"


def _default_user_dir() -> Path:
    """Return the default user skills directory (``~/.pnlclaw/skills/``)."""
    return Path.home() / ".pnlclaw" / "skills"


class SkillRegistry:
    """Registry of loaded skills from multiple sources.

    Loads skills from bundled, user, workspace, and extra directories.
    When multiple sources provide a skill with the same name, the higher-
    priority source wins (workspace > user > bundled > extra).

    Args:
        config: Skills configuration with extra dirs and enable overrides.
        bundled_dir: Override for the bundled skills directory.
        user_dir: Override for the user skills directory.
        workspace_dir: Optional workspace-level skills directory.
    """

    def __init__(
        self,
        config: SkillsConfig | None = None,
        *,
        bundled_dir: str | Path | None = None,
        user_dir: str | Path | None = None,
        workspace_dir: str | Path | None = None,
    ) -> None:
        self._config = config or SkillsConfig()
        self._bundled_dir = Path(bundled_dir) if bundled_dir else _default_bundled_dir()
        self._user_dir = Path(user_dir) if user_dir else _default_user_dir()
        self._workspace_dir = Path(workspace_dir) if workspace_dir else None
        self._skills: dict[str, Skill] = {}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """Whether skills have been loaded at least once."""
        return self._loaded

    def load(self) -> None:
        """Load skills from all configured sources.

        Skills are deduplicated by name with source priority:
        workspace > user > bundled > extra.

        Skills explicitly disabled in config are excluded.
        """
        candidates: dict[str, Skill] = {}

        # Load from each source
        sources: list[tuple[Path, SkillSource]] = []

        # Extra dirs (lowest priority)
        for extra_path in self._config.extra_dirs:
            sources.append((Path(extra_path), SkillSource.EXTRA))

        # Bundled
        sources.append((self._bundled_dir, SkillSource.BUNDLED))

        # User
        sources.append((self._user_dir, SkillSource.USER))

        # Workspace (highest priority)
        if self._workspace_dir is not None:
            sources.append((self._workspace_dir, SkillSource.WORKSPACE))

        for root, source in sources:
            loader = SkillLoader(root, source, self._config.limits)
            for skill in loader.scan():
                existing = candidates.get(skill.name)
                if existing is None:
                    candidates[skill.name] = skill
                else:
                    # Higher priority source wins
                    existing_prio = _SOURCE_PRIORITY.get(existing.source, 0)
                    new_prio = _SOURCE_PRIORITY.get(skill.source, 0)
                    if new_prio >= existing_prio:
                        logger.debug(
                            "skill_override",
                            name=skill.name,
                            old_source=existing.source.value,
                            new_source=skill.source.value,
                        )
                        candidates[skill.name] = skill

        # Apply enable/disable overrides
        self._skills = {}
        for name, skill in candidates.items():
            enabled = self._config.enabled.get(name)
            if enabled is False:
                logger.debug("skill_disabled", name=name)
                continue
            self._skills[name] = skill

        self._loaded = True
        logger.debug(
            "skills_loaded",
            count=len(self._skills),
            names=sorted(self._skills.keys()),
        )

    def refresh(self) -> None:
        """Re-scan all sources and reload skills."""
        self._skills.clear()
        self._loaded = False
        self.load()

    def get(self, name: str) -> Skill | None:
        """Look up a skill by name.

        Args:
            name: The skill name to look up.

        Returns:
            The Skill if found, or None.
        """
        self._ensure_loaded()
        return self._skills.get(name)

    def list_skills(self) -> list[Skill]:
        """Return all loaded skills, sorted by name.

        Returns:
            A sorted list of all loaded Skill objects.
        """
        self._ensure_loaded()
        return sorted(self._skills.values(), key=lambda s: s.name)

    def list_eligible(self, available_tools: list[str] | None = None) -> list[Skill]:
        """Return skills whose tool requirements are satisfied.

        A skill is eligible if all entries in its ``requires_tools`` list
        are present in ``available_tools``.  Skills with no tool requirements
        are always eligible.

        Args:
            available_tools: List of tool names currently available.
                If None, all skills are considered eligible.

        Returns:
            A sorted list of eligible Skill objects.
        """
        self._ensure_loaded()
        tool_set = set(available_tools) if available_tools is not None else None

        eligible: list[Skill] = []
        for skill in self._skills.values():
            if tool_set is not None and skill.frontmatter.requires_tools:
                if not all(t in tool_set for t in skill.frontmatter.requires_tools):
                    continue
            eligible.append(skill)

        return sorted(eligible, key=lambda s: s.name)

    def list_summaries(self) -> list[SkillSummary]:
        """Return lightweight summaries of all loaded skills.

        Returns:
            A sorted list of SkillSummary objects.
        """
        self._ensure_loaded()
        return [
            SkillSummary(
                name=s.name,
                description=s.description,
                source=s.source,
                tags=s.frontmatter.tags,
                user_invocable=s.frontmatter.user_invocable,
                model_invocable=s.frontmatter.model_invocable,
            )
            for s in sorted(self._skills.values(), key=lambda s: s.name)
        ]

    def skill_names(self) -> list[str]:
        """Return sorted list of all loaded skill names.

        Returns:
            Sorted list of skill name strings.
        """
        self._ensure_loaded()
        return sorted(self._skills.keys())

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        self._ensure_loaded()
        return name in self._skills

    def _ensure_loaded(self) -> None:
        """Load skills if not yet loaded (lazy initialization)."""
        if not self._loaded:
            self.load()
