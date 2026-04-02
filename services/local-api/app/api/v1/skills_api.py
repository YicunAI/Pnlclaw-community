"""Skills management endpoints.

Provides listing, detail view, enable/disable, create/edit/delete, and
refresh for loaded skills.  User-created skills are persisted as SKILL.md
files under ``~/.pnlclaw/skills/<name>/SKILL.md``.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import AuthenticatedUser, get_settings_service, get_skill_registry, optional_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/skills", tags=["skills"])

_USER_SKILLS_DIR = Path.home() / ".pnlclaw" / "skills"
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _user_skills_dir(user: AuthenticatedUser) -> Path:
    """Return the skills directory scoped to the current user."""
    if user.id == "local":
        return _USER_SKILLS_DIR
    return Path.home() / ".pnlclaw" / "users" / user.id / "skills"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SkillEnableRequest(BaseModel):
    enabled: bool = Field(..., description="Whether to enable or disable the skill")


class SkillCreateRequest(BaseModel):
    """Create or import a skill.  The server builds the SKILL.md file."""

    name: str = Field(..., min_length=1, max_length=64, description="Skill identifier (a-z, 0-9, - _)")
    description: str = Field("", max_length=256, description="Short description")
    tags: list[str] = Field(default_factory=list, description="Categorisation tags")
    content: str = Field(..., min_length=1, description="Markdown body of the skill")
    user_invocable: bool = Field(True)
    model_invocable: bool = Field(True)
    requires_tools: list[str] = Field(default_factory=list)


class SkillUpdateRequest(BaseModel):
    """Update an existing user skill."""

    description: str | None = Field(None, max_length=256)
    tags: list[str] | None = None
    content: str | None = Field(None, min_length=1)
    user_invocable: bool | None = None
    model_invocable: bool | None = None
    requires_tools: list[str] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skill_to_dict(s: Any, enabled_map: dict[str, bool] | None = None) -> dict[str, Any]:
    name = s.name
    enabled = True
    if enabled_map is not None and name in enabled_map:
        enabled = enabled_map[name]
    return {
        "name": name,
        "description": s.description,
        "source": s.source.value if hasattr(s.source, "value") else str(s.source),
        "tags": s.frontmatter.tags if hasattr(s, "frontmatter") else [],
        "user_invocable": s.frontmatter.user_invocable if hasattr(s, "frontmatter") else True,
        "model_invocable": s.frontmatter.model_invocable if hasattr(s, "frontmatter") else True,
        "requires_tools": s.frontmatter.requires_tools if hasattr(s, "frontmatter") else [],
        "file_path": s.file_path,
        "enabled": enabled,
    }


def _rebuild_registry(registry: Any, settings_svc: Any) -> None:
    if registry is None or settings_svc is None:
        return
    try:
        from pnlclaw_agent.skills.types import SkillsConfig

        cfg = settings_svc.get_skills_config()
        new_config = SkillsConfig(
            extra_dirs=cfg.get("extra_dirs", []),
            enabled=cfg.get("enabled", {}),
        )
        registry._config = new_config
        registry.refresh()
    except Exception:
        logger.warning("Failed to rebuild skill registry", exc_info=True)


def _build_skill_md(
    name: str,
    description: str,
    tags: list[str],
    content: str,
    *,
    user_invocable: bool = True,
    model_invocable: bool = True,
    requires_tools: list[str] | None = None,
    version: str = "0.1.0",
) -> str:
    """Build a complete SKILL.md string with YAML frontmatter."""
    tags_str = "[" + ", ".join(tags) + "]" if tags else "[]"
    tools_str = "[" + ", ".join(requires_tools or []) + "]"

    frontmatter = (
        f"---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"version: {version}\n"
        f"tags: {tags_str}\n"
        f"user_invocable: {'true' if user_invocable else 'false'}\n"
        f"model_invocable: {'true' if model_invocable else 'false'}\n"
        f"requires_tools: {tools_str}\n"
        f"---\n"
    )

    body = content.strip()
    if not body.startswith("#"):
        body = f"# {name}\n\n{body}"

    return f"{frontmatter}\n{body}\n"


def _write_user_skill(name: str, md_content: str) -> Path:
    """Write a SKILL.md into the default user skills directory."""
    skill_dir = _USER_SKILLS_DIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(md_content, encoding="utf-8")
    return skill_file


def _write_user_skill_scoped(base_dir: Path, name: str, md_content: str) -> Path:
    """Write a SKILL.md into a user-scoped skills directory."""
    skill_dir = base_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(md_content, encoding="utf-8")
    return skill_file


def _parse_existing_skill_md(file_path: Path) -> dict[str, Any]:
    """Parse frontmatter + body from an existing SKILL.md."""
    text = file_path.read_text(encoding="utf-8")
    result: dict[str, Any] = {"content": text, "frontmatter": {}}

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            result["body"] = parts[2].strip()
            # Simple YAML-like frontmatter parse
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    result["frontmatter"][key.strip()] = val.strip()
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_skills(
    registry: Any = Depends(get_skill_registry),
    settings_svc: Any = Depends(get_settings_service),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    """List all loaded skills with their enabled state."""
    if registry is None:
        return {"skills": [], "count": 0, "message": "Skill registry not initialized"}

    enabled_map: dict[str, bool] = {}
    if settings_svc is not None:
        cfg = settings_svc.get_skills_config()
        enabled_map = cfg.get("enabled", {})

    skills = registry.list_skills()
    return {
        "skills": [_skill_to_dict(s, enabled_map) for s in skills],
        "count": len(skills),
    }


@router.post("/create")
async def create_skill(
    body: SkillCreateRequest,
    registry: Any = Depends(get_skill_registry),
    settings_svc: Any = Depends(get_settings_service),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    """Create a new user skill (scoped to current user)."""
    name = body.name.strip().lower().replace(" ", "-")
    if not _SAFE_NAME_RE.match(name):
        raise HTTPException(
            400,
            "Invalid skill name. Use only letters, numbers, hyphens, underscores (1-64 chars).",
        )

    skills_dir = _user_skills_dir(user)
    skill_dir = skills_dir / name
    if skill_dir.exists() and (skill_dir / "SKILL.md").exists():
        raise HTTPException(409, f"Skill '{name}' already exists. Use PUT to update.")

    md = _build_skill_md(
        name=name,
        description=body.description,
        tags=body.tags,
        content=body.content,
        user_invocable=body.user_invocable,
        model_invocable=body.model_invocable,
        requires_tools=body.requires_tools,
    )
    file_path = _write_user_skill_scoped(skills_dir, name, md)

    _rebuild_registry(registry, settings_svc)

    return {
        "name": name,
        "file_path": str(file_path),
        "created": True,
    }


@router.get("/{name}")
async def get_skill(
    name: str,
    registry: Any = Depends(get_skill_registry),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    """Get detailed information about a specific skill."""
    if registry is None:
        raise HTTPException(503, "Skill registry not initialized")

    skill = registry.get(name)
    if skill is None:
        raise HTTPException(404, f"Skill '{name}' not found")

    return {
        "name": skill.name,
        "description": skill.description,
        "source": skill.source.value if hasattr(skill.source, "value") else str(skill.source),
        "tags": skill.frontmatter.tags,
        "user_invocable": skill.frontmatter.user_invocable,
        "model_invocable": skill.frontmatter.model_invocable,
        "requires_tools": skill.frontmatter.requires_tools,
        "requires_env": skill.frontmatter.requires_env,
        "version": skill.frontmatter.version,
        "author": skill.frontmatter.author,
        "file_path": skill.file_path,
        "content": skill.content,
    }


@router.put("/{name}")
async def update_skill(
    name: str,
    body: SkillUpdateRequest,
    registry: Any = Depends(get_skill_registry),
    settings_svc: Any = Depends(get_settings_service),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    """Update a user-created skill's content or metadata."""
    if registry is None:
        raise HTTPException(503, "Skill registry not initialized")

    skill = registry.get(name)
    if skill is None:
        raise HTTPException(404, f"Skill '{name}' not found")

    source = skill.source.value if hasattr(skill.source, "value") else str(skill.source)
    if source != "user":
        raise HTTPException(403, "Only user-created skills can be edited")

    description = body.description if body.description is not None else skill.description
    tags = body.tags if body.tags is not None else skill.frontmatter.tags
    content = body.content if body.content is not None else skill.content
    user_invocable = body.user_invocable if body.user_invocable is not None else skill.frontmatter.user_invocable
    model_invocable = body.model_invocable if body.model_invocable is not None else skill.frontmatter.model_invocable
    requires_tools = body.requires_tools if body.requires_tools is not None else skill.frontmatter.requires_tools

    md = _build_skill_md(
        name=name,
        description=description,
        tags=tags,
        content=content,
        user_invocable=user_invocable,
        model_invocable=model_invocable,
        requires_tools=requires_tools,
        version=skill.frontmatter.version,
    )
    skills_dir = _user_skills_dir(user)
    file_path = _write_user_skill_scoped(skills_dir, name, md)

    _rebuild_registry(registry, settings_svc)

    return {"name": name, "file_path": str(file_path), "updated": True}


@router.delete("/{name}")
async def delete_skill(
    name: str,
    registry: Any = Depends(get_skill_registry),
    settings_svc: Any = Depends(get_settings_service),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    """Delete a user-created skill."""
    if registry is None:
        raise HTTPException(503, "Skill registry not initialized")

    skill = registry.get(name)
    if skill is not None:
        source = skill.source.value if hasattr(skill.source, "value") else str(skill.source)
        if source != "user":
            raise HTTPException(403, "Only user-created skills can be deleted")

    skills_dir = _user_skills_dir(user)
    skill_dir = skills_dir / name
    if skill_dir.exists():
        shutil.rmtree(skill_dir)

    _rebuild_registry(registry, settings_svc)

    return {"name": name, "deleted": True}


@router.put("/{name}/enable")
async def toggle_skill(
    name: str,
    body: SkillEnableRequest,
    registry: Any = Depends(get_skill_registry),
    settings_svc: Any = Depends(get_settings_service),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    """Enable or disable a skill, persisted to settings."""
    if registry is None:
        raise HTTPException(503, "Skill registry not initialized")

    if settings_svc is not None:
        cfg = settings_svc.get_skills_config()
        enabled = cfg.get("enabled", {})
        enabled[name] = body.enabled
        settings_svc.update_skills_config({"enabled": enabled})

    if hasattr(registry, "_config") and registry._config is not None:
        registry._config.enabled[name] = body.enabled

    return {"name": name, "enabled": body.enabled}


@router.post("/refresh")
async def refresh_skills(
    registry: Any = Depends(get_skill_registry),
    settings_svc: Any = Depends(get_settings_service),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    """Re-scan skill directories and reload all skills."""
    if registry is None:
        raise HTTPException(503, "Skill registry not initialized")

    _rebuild_registry(registry, settings_svc)
    skills = registry.list_skills()
    return {"refreshed": True, "count": len(skills)}
