"""Skill configuration -- loads skills settings from user config file.

Reads the ``skills`` key from ``~/.pnlclaw/config.yaml`` and returns
a validated SkillsConfig instance.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pnlclaw_agent.skills.types import SkillsConfig

try:
    import structlog

    logger: Any = structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path.home() / ".pnlclaw" / "config.yaml"


def load_skills_config(
    config_path: str | Path | None = None,
) -> SkillsConfig:
    """Load skills configuration from the user config file.

    Reads the ``skills`` key from the YAML config file at
    ``~/.pnlclaw/config.yaml`` (or the given override path).
    Returns a default SkillsConfig if the file is missing or
    contains no ``skills`` section.

    Args:
        config_path: Optional override for the config file path.
            Defaults to ``~/.pnlclaw/config.yaml``.

    Returns:
        A validated SkillsConfig instance.
    """
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH

    if not path.is_file():
        logger.debug("skills_config_not_found", path=str(path))
        return SkillsConfig()

    try:
        import yaml

        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except ImportError:
        logger.warning("pyyaml_not_available", msg="Cannot parse config without PyYAML")
        return SkillsConfig()
    except Exception as exc:
        logger.warning("skills_config_read_error", path=str(path), error=str(exc))
        return SkillsConfig()

    if not isinstance(data, dict):
        return SkillsConfig()

    skills_data = data.get("skills")
    if not isinstance(skills_data, dict):
        return SkillsConfig()

    try:
        return SkillsConfig(**skills_data)
    except Exception as exc:
        logger.warning("skills_config_parse_error", error=str(exc))
        return SkillsConfig()
