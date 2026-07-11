"""skills.py — REST for the Skills Hub (view / sync / review / enable-disable).

Skills are Agent Skills (SKILL.md folders). This exposes the local set with their
enabled/source state, the allowlisted GitHub sources, and the sync + enable/disable
controls. Synced skills arrive DISABLED and can't influence a task until a human
reviews the SKILL.md and enables it (the review gate lives in core/skills + skill_sync).
"""
import os
from urllib.error import URLError, HTTPError

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import skills as skill_lib
from core import skill_sync

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
def list_skills():
    """Every local skill with its enabled state + provenance (for the Skills tab)."""
    return {"skills": skill_lib.all_catalog()}


@router.get("/sources")
def list_sources():
    return {"sources": [{"name": s.get("name"), "repo": s.get("repo"),
                         "branch": s.get("branch", "main")} for s in skill_sync._sources()]}


@router.get("/available")
def available(source: str):
    try:
        return {"available": skill_sync.list_available(source)}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (URLError, HTTPError) as e:
        raise HTTPException(502, f"could not reach GitHub: {e}")


class SyncIn(BaseModel):
    source: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)


@router.post("/sync")
def sync(body: SyncIn):
    try:
        result = skill_sync.sync_skill(body.source, body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (URLError, HTTPError) as e:
        raise HTTPException(502, f"could not reach GitHub: {e}")
    return {"ok": True, "synced": result, "skills": skill_lib.all_catalog()}


@router.get("/{name}")
def view(name: str):
    """The SKILL.md body + the security scan — so a human can REVIEW a synced skill
    (and see its risky patterns) before enabling it."""
    s = skill_lib.get(name)
    if not s:
        raise HTTPException(404, "skill not found")
    return {"name": s.name, "description": s.description, "enabled": s.enabled,
            "source": s.source, "body": s.body, "scan": skill_lib.scan(name)}


@router.post("/{name}/enable")
def enable(name: str, force: bool = False):
    """Enable a skill. Blocked (409) if the scan flags it 'risky' unless force=true —
    the security gate on top of the human review gate."""
    if not skill_lib.get(name):
        raise HTTPException(404, "skill not found")
    try:
        skill_lib.set_enabled(name, True, force=force)
    except skill_lib.SkillBlocked as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "skills": skill_lib.all_catalog()}


@router.post("/{name}/disable")
def disable(name: str):
    if not skill_lib.get(name):
        raise HTTPException(404, "skill not found")
    skill_lib.set_enabled(name, False)
    return {"ok": True, "skills": skill_lib.all_catalog()}
