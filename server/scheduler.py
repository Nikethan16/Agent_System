"""
scheduler.py — run saved tasks on a schedule (once / interval / daily / weekly).

A lightweight scheduler ON TOP of the persistent job queue: it decides WHEN a task
is due, and jobs.py RUNS it unattended (same auto-approve path as any background job;
policy hard-blocks still apply). Schedules live in SQLite, so they SURVIVE a restart.
No external services — no cron daemon, no Redis.

Schedule kinds + their `spec`:
  once      ISO datetime (UTC),     e.g. "2026-06-20T09:00:00"
  interval  seconds between runs,   e.g. "3600"  (hourly)
  daily     "HH:MM" (UTC),          e.g. "09:00" (every day at 09:00)
  weekly    "DOW HH:MM" (DOW 0=Mon..6=Sun, UTC), e.g. "0 09:00" (Mondays 09:00)
All times are UTC to stay deterministic; the UI can present them in local time.
"""
import os
import time
import logging
import threading
from datetime import datetime, timezone, timedelta

from sqlmodel import SQLModel, Field, Session as DBSession, select

from .db import engine, _uuid, _now, safe_id

log = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()
_TICK = int(os.environ.get("AGENT_SCHEDULER_TICK", "30"))   # seconds between due-checks
_MAX_USD_CEILING = float(os.environ.get("AGENT_MAX_USD_CEILING", "5.0"))
_MAX_ITER_CEILING = int(os.environ.get("AGENT_MAX_ITER_CEILING", "60"))


class Schedule(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(default="", index=True)
    text: str = ""                  # the prompt/task to run
    kind: str = "once"              # once | interval | daily | weekly
    spec: str = ""                  # see module docstring
    enabled: bool = True
    next_run_at: str = ""           # ISO (UTC); "" = nothing scheduled
    last_run_at: str = ""
    last_job_id: str = ""
    max_usd: float = 0.5
    max_iterations: int = 20
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


# ---- next-run math (pure + unit-testable; all UTC) --------------------------
def _parse_iso(s):
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _hhmm(s):
    try:
        hh, mm = (s or "09:00").split(":")
        return max(0, min(23, int(hh))), max(0, min(59, int(mm)))
    except Exception:
        return 9, 0


def compute_next(kind: str, spec: str, after: datetime = None):
    """The next run time (ISO UTC) strictly AFTER `after` (default: now).
    Returns None for a 'once' schedule whose time has already passed (no further runs)."""
    now = after or datetime.now(timezone.utc)
    kind = (kind or "once").lower()
    if kind == "once":
        dt = _parse_iso(spec)
        return dt.isoformat() if (dt and dt > now) else None
    if kind == "interval":
        try:
            secs = max(10, int(float(spec)))
        except (TypeError, ValueError):
            secs = 3600
        return (now + timedelta(seconds=secs)).isoformat()
    if kind == "daily":
        hh, mm = _hhmm(spec)
        cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand <= now:
            cand += timedelta(days=1)
        return cand.isoformat()
    if kind == "weekly":
        parts = (spec or "").split()
        dow = (int(parts[0]) % 7) if (parts and parts[0].lstrip("-").isdigit()) else 0
        hh, mm = _hhmm(parts[1] if len(parts) > 1 else "09:00")
        cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        cand += timedelta(days=(dow - cand.weekday()) % 7)
        if cand <= now:
            cand += timedelta(days=7)
        return cand.isoformat()
    return None


# ---- CRUD -------------------------------------------------------------------
def create(session_id: str, text: str, kind: str = "once", spec: str = "",
           max_usd: float = 0.5, max_iterations: int = 20) -> dict:
    safe_id(session_id)                       # reject crafted ids before fs use (in jobs)
    nxt = compute_next(kind, spec)
    with DBSession(engine) as s:
        sch = Schedule(
            session_id=session_id, text=text, kind=kind, spec=spec,
            next_run_at=nxt or "", enabled=bool(nxt),
            max_usd=max(0.0, min(float(max_usd), _MAX_USD_CEILING)),
            max_iterations=max(1, min(int(max_iterations), _MAX_ITER_CEILING)),
        )
        s.add(sch)
        s.commit()
        s.refresh(sch)
        out = sch.model_dump()
    start_scheduler()
    return out


def list_all(session_id: str = None) -> list:
    with DBSession(engine) as s:
        rows = s.exec(select(Schedule).order_by(Schedule.created_at.desc())).all()
    return [r.model_dump() for r in rows if not session_id or r.session_id == session_id]


def get(sid: str):
    with DBSession(engine) as s:
        sch = s.get(Schedule, sid)
        return sch.model_dump() if sch else None


def delete(sid: str) -> bool:
    with DBSession(engine) as s:
        sch = s.get(Schedule, sid)
        if not sch:
            return False
        s.delete(sch)
        s.commit()
        return True


def set_enabled(sid: str, enabled: bool):
    with DBSession(engine) as s:
        sch = s.get(Schedule, sid)
        if not sch:
            return None
        sch.enabled = bool(enabled)
        # Re-arm next_run when re-enabling (recurring kinds); leave 'once' as-is.
        if sch.enabled and not sch.next_run_at:
            sch.next_run_at = compute_next(sch.kind, sch.spec) or ""
        sch.updated_at = _now()
        s.add(sch)
        s.commit()
        s.refresh(sch)
        return sch.model_dump()


# ---- firing -----------------------------------------------------------------
def _enqueue(sch: "Schedule") -> str:
    from . import jobs   # late import (jobs imports chat which imports a lot)
    return jobs.enqueue(sch.session_id, sch.text, sch.max_usd, sch.max_iterations)


def run_now(sid: str):
    """Fire a schedule immediately (manual trigger), independent of its next_run_at."""
    from . import db
    with DBSession(engine) as s:
        sch = s.get(Schedule, sid)
        if not sch:
            return None
        if not db.get_session(sch.session_id):
            return {"error": "session no longer exists"}
        jid = _enqueue(sch)
        sch.last_run_at, sch.last_job_id, sch.updated_at = _now(), jid, _now()
        s.add(sch)
        s.commit()
        return {"job_id": jid}


def run_due(now: datetime = None) -> list:
    """Enqueue every enabled schedule whose next_run_at has arrived, then advance it
    (or disable a finished one-shot). Returns the ids fired. Pure of sleeping so it's
    unit-testable."""
    from . import db
    now = now or datetime.now(timezone.utc)
    fired = []
    with DBSession(engine) as s:
        rows = s.exec(select(Schedule).where(Schedule.enabled == True)).all()  # noqa: E712
        for sch in rows:
            nxt = _parse_iso(sch.next_run_at)
            if not nxt or nxt > now:
                continue
            if not db.get_session(sch.session_id):     # target chat gone — stop it
                sch.enabled, sch.updated_at = False, _now()
                s.add(sch)
                continue
            jid = _enqueue(sch)
            after = compute_next(sch.kind, sch.spec, after=now)
            sch.last_run_at, sch.last_job_id = _now(), jid
            sch.next_run_at = after or ""
            if not after:
                sch.enabled = False                    # one-shot complete
            sch.updated_at = _now()
            s.add(sch)
            fired.append(sch.id)
        s.commit()
    return fired


def _loop():
    while True:
        try:
            run_due()
        except Exception as e:                          # never let the loop die
            log.warning("scheduler tick failed: %s", e)
        time.sleep(_TICK)


def start_scheduler():
    """Idempotent: start the background scheduler thread."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, daemon=True).start()
