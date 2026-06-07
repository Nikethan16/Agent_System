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
    created_at: str = Field(default_factory=_now)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def spent_today() -> float:
    with DBSession(engine) as s:
        rows = s.exec(select(Spend).where(Spend.day == _today())).all()
    return round(sum(r.usd for r in rows), 6)


def record(usd: float) -> None:
    if not usd or usd <= 0:
        return
    with DBSession(engine) as s:
        s.add(Spend(day=_today(), usd=float(usd)))
        s.commit()


def over_cap() -> bool:
    return DAILY_CAP > 0 and spent_today() >= DAILY_CAP


def status() -> dict:
    spent = spent_today()
    return {
        "spent_today": spent,
        "cap": DAILY_CAP if DAILY_CAP > 0 else None,
        "remaining": round(max(0.0, DAILY_CAP - spent), 6) if DAILY_CAP > 0 else None,
    }
