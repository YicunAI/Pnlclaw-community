"""Skill loader -- scans directories for SKILL.md files and parses frontmatter.

Handles YAML frontmatter extraction, file size limits, path traversal
protection, and multi-source loading with priority ordering.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from pnlclaw_agent.skills.types import (
    Skill,
    SkillFrontmatter,
    SkillsLimits,
    SkillSource,
)

try:
    import structlog

    logger: Any = structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

_SKILL_FILENAME = "SKILL.md"
_FRONTMATTER_DELIMITER = "---"


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Split a SKILL.md file into frontmatter dict and body content.

    Frontmatter is expected between two ``---`` delimiters at the start of
    the file.  If no valid frontmatter is found, returns an empty dict and
    the full raw text as body.

    Args:
        raw: The full text content of a SKILL.md file.

    Returns:
        A tuple of (frontmatter_dict, body_content).
    """
    stripped = raw.lstrip("\ufeff")  # strip BOM if present
    if not stripped.startswith(_FRONTMATTER_DELIMITER):
        return {}, stripped

    # Find second delimiter
    rest = stripped[len(_FRONTMATTER_DELIMITER) :]
    end_idx = rest.find(f"\n{_FRONTMATTER_DELIMITER}")
    if end_idx == -1:
        return {}, stripped

    yaml_block = rest[:end_idx]
    body_start = end_idx + len(_FRONTMATTER_DELIMITER) + 1  # +1 for newline
    body = rest[body_start:]
    # Skip the closing delimiter line
    if body.startswith(_FRONTMATTER_DELIMITER):
        body = body[len(_FRONTMATTER_DELIMITER) :]
    if body.startswith("\n"):
        body = body[1:]

    try:
        data = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        logger.warning("invalid_skill_frontmatter", error=str(exc))
        return {}, stripped

    if not isinstance(data, dict):
        return {}, stripped

    return data, body


def _is_safe_path(file_path: Path, root_dir: Path) -> bool:
    """Check that file_path is contained within root_dir (path traversal guard).

    Args:
        file_path: Resolved absolute path to the skill file.
        root_dir: Resolved absolute path to the skill root directory.

    Returns:
        True if file_path is inside root_dir.
    """
    try:
        file_resolved = file_path.resolve()
        root_resolved = root_dir.resolve()
        # Check the file is under the root directory
        file_resolved.relative_to(root_resolved)
        return True
    except ValueError:
        return False


class SkillLoader:
    """Loads skills from a directory by scanning for ``<name>/SKILL.md`` files.

    Each subdirectory that contains a SKILL.md file is treated as a skill.
    The loader parses YAML frontmatter, enforces file size limits, and
    validates path safety.

    Args:
        root_dir: Path to the directory containing skill subdirectories.
        source: The source classification for skills loaded from this directory.
        limits: Resource limits for file size enforcement.
    """

    def __init__(
        self,
        root_dir: str | Path,
        source: SkillSource,
        limits: SkillsLimits | None = None,
    ) -> None:
        self._root_dir = Path(root_dir).resolve()
        self._source = source
        self._limits = limits or SkillsLimits()

    @property
    def root_dir(self) -> Path:
        """The root directory this loader scans."""
        return self._root_dir

    @property
    def source(self) -> SkillSource:
        """The source classification for skills from this loader."""
        return self._source

    def scan(self) -> list[Skill]:
        """Scan the root directory for skill subdirectories and load them.

        Each immediate subdirectory containing a SKILL.md file is treated as
        a skill.  Files exceeding the size limit or failing path traversal
        checks are skipped with a warning.

        Returns:
            A list of loaded Skill objects, sorted by name.
        """
        if not self._root_dir.is_dir():
            logger.debug("skill_dir_not_found", path=str(self._root_dir))
            return []

        skills: list[Skill] = []
        try:
            entries = sorted(self._root_dir.iterdir())
        except PermissionError:
            logger.warning("skill_dir_permission_denied", path=str(self._root_dir))
            return []

        for entry in entries:
            if not entry.is_dir():
                continue
            skill_file = entry / _SKILL_FILENAME
            if not skill_file.is_file():
                continue

            skill = self._load_skill(skill_file, entry)
            if skill is not None:
                skills.append(skill)

        return sorted(skills, key=lambda s: s.name)

    def load_single(self, skill_dir: str | Path) -> Skill | None:
        """Load a single skill from the given directory.

        Args:
            skill_dir: Path to a directory containing a SKILL.md file.

        Returns:
            A loaded Skill, or None if loading fails.
        """
        skill_dir = Path(skill_dir).resolve()
        skill_file = skill_dir / _SKILL_FILENAME
        if not skill_file.is_file():
            logger.debug("skill_file_not_found", path=str(skill_file))
            return None
        return self._load_skill(skill_file, skill_dir)

    def _load_skill(self, skill_file: Path, skill_dir: Path) -> Skill | None:
        """Load and parse a single SKILL.md file.

        Args:
            skill_file: Absolute path to the SKILL.md file.
            skill_dir: Directory containing the SKILL.md file.

        Returns:
            A loaded Skill, or None if validation fails.
        """
        # Path traversal protection
        if not _is_safe_path(skill_file, self._root_dir):
            logger.warning(
                "skill_path_traversal_blocked",
                file=str(skill_file),
                root=str(self._root_dir),
            )
            return None

        # File size check
        try:
            file_size = skill_file.stat().st_size
        except OSError as exc:
            logger.warning("skill_stat_failed", path=str(skill_file), error=str(exc))
            return None

        if file_size > self._limits.max_skill_file_bytes:
            logger.warning(
                "skill_file_too_large",
                path=str(skill_file),
                size=file_size,
                limit=self._limits.max_skill_file_bytes,
            )
            return None

        # Read and parse
        try:
            raw = skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("skill_read_failed", path=str(skill_file), error=str(exc))
            return None

        fm_data, body = _parse_frontmatter(raw)

        # Build frontmatter with fallback to directory name
        dir_name = skill_dir.name
        if "name" not in fm_data:
            fm_data["name"] = dir_name

        try:
            frontmatter = SkillFrontmatter(**fm_data)
        except Exception as exc:
            logger.warning(
                "skill_frontmatter_invalid",
                path=str(skill_file),
                error=str(exc),
            )
            return None

        return Skill(
            name=frontmatter.name,
            description=frontmatter.description,
            file_path=str(skill_file),
            base_dir=str(skill_dir),
            source=self._source,
            frontmatter=frontmatter,
            content=body.strip(),
        )
