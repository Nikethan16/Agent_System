"""
spend.py — a global daily spend cap (a safety net above the per-run Budget).

The per-run Budget caps a single task. This adds a CUMULATIVE daily ceiling across
all runs so a busy day (or a stuck loop of runs) can't quietly rack up cost. Set
AGENT_DAILY_USD_CAP in .env; 0 / unset = unlimited (default, so behaviour is unchanged
until you opt in). Spend is recorded per UTC day in SQLite and resets at midnight UTC.
"""
import os
from datetime import datetime, timezone

from sqlmodel import SQLModel, Field, Session as DBSession, select

from .db import engine, _uuid, _now

DAILY_CAP = float(os.environ.get("AGENT_DAILY_USD_CAP", "0") or 0.0)  # 0 = unlimited


class Spend(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    day: str = Field(default="", index=True)   # UTC date, e.g. "2026-06-03"
    usd: float = 0.0
    project_id: str = Field(default="", index=True)   # "" = standalone chat (no project)
    created_at: str = Field(default_factory=_now)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def spent_today() -> float:
    with DBSession(engine) as s:
        rows = s.exec(select(Spend).where(Spend.day == _today())).all()
    return round(sum(r.usd for r in rows), 6)


def record(usd: float, project_id: str = "") -> None:
    if not usd or usd <= 0:
        return
    with DBSession(engine) as s:
        s.add(Spend(day=_today(), usd=float(usd), project_id=project_id or ""))
        s.commit()


def spent_by_project(project_id: str) -> float:
    """Cumulative (all-time) spend attributed to a project."""
    if not project_id:
        return 0.0
    with DBSession(engine) as s:
        rows = s.exec(select(Spend).where(Spend.project_id == project_id)).all()
    return round(sum(r.usd for r in rows), 6)


def project_over_cap(project_id: str, cap: float) -> bool:
    """True if a project has a positive budget cap and has reached it."""
    return bool(project_id) and cap and cap > 0 and spent_by_project(project_id) >= cap


def project_status(project_id: str, cap: float = 0.0) -> dict:
    spent = spent_by_project(project_id)
    cap = cap if cap and cap > 0 else None
    return {
        "project_id": project_id,
        "spent": spent,
        "cap": cap,
        "remaining": round(max(0.0, cap - spent), 6) if cap else None,
    }


def over_cap() -> bool:
    return DAILY_CAP > 0 and spent_today() >= DAILY_CAP


def status() -> dict:
    spent = spent_today()
    return {
        "spent_today": spent,
        "cap": DAILY_CAP if DAILY_CAP > 0 else None,
        "remaining": round(max(0.0, DAILY_CAP - spent), 6) if DAILY_CAP > 0 else None,
    }
