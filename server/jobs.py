"""
jobs.py — a simple, persistent task queue (roadmap #2).

Jobs are stored in SQLite and run by a background worker thread, so a queued task
SURVIVES a restart and runs unattended. This works with ZERO external services. For
heavier/distributed use you can later swap this for Redis + RQ (see docs/PLACEHOLDERS.md)
without changing the API surface.

Background jobs run with no human present, so they use the default auto-approve path
(the deterministic policy hard-blocks still apply).
"""
import os
import time
import threading

from sqlmodel import SQLModel, Field, Session as DBSession, select

from .db import engine, _uuid, _now, safe_id
from core.llm import Budget

_started = False
_lock = threading.Lock()

# Same server ceilings as the live WebSocket path — a queued job can't request a
# runaway budget either.
_MAX_USD_CEILING = float(os.environ.get("AGENT_MAX_USD_CEILING", "5.0"))
_MAX_ITER_CEILING = int(os.environ.get("AGENT_MAX_ITER_CEILING", "60"))


class Job(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(default="", index=True)
    text: str = ""
    status: str = "queued"          # queued | running | done | error
    result: str = ""
    max_usd: float = 0.5
    max_iterations: int = 20
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


def enqueue(session_id: str, text: str, max_usd: float = 0.5, max_iterations: int = 20) -> str:
    safe_id(session_id)   # reject crafted ids before they reach the filesystem
    max_usd = max(0.0, min(float(max_usd), _MAX_USD_CEILING))
    max_iterations = max(1, min(int(max_iterations), _MAX_ITER_CEILING))
    with DBSession(engine) as s:
        j = Job(session_id=session_id, text=text, max_usd=max_usd, max_iterations=max_iterations)
        s.add(j)
        s.commit()
        s.refresh(j)
        jid = j.id
    start_worker()
    return jid


def list_jobs(session_id: str = None) -> list:
    with DBSession(engine) as s:
        rows = s.exec(select(Job).order_by(Job.created_at.desc())).all()
    return [r.model_dump() for r in rows if not session_id or r.session_id == session_id]


def get_job(jid: str):
    with DBSession(engine) as s:
        j = s.get(Job, jid)
        return j.model_dump() if j else None


def _recover_stale():
    """On startup, re-queue any job left 'running' by a process that died mid-flight,
    so in-flight work actually survives a restart (the queue's whole point)."""
    with DBSession(engine) as s:
        for j in s.exec(select(Job).where(Job.status == "running")).all():
            j.status, j.updated_at = "queued", _now()
            s.add(j)
        s.commit()


def _claim_next():
    with DBSession(engine) as s:
        j = s.exec(select(Job).where(Job.status == "queued").order_by(Job.created_at)).first()
        if not j:
            return None
        j.status, j.updated_at = "running", _now()
        s.add(j)
        s.commit()
        s.refresh(j)
        return j.model_dump()


def _finish(jid, status, result):
    with DBSession(engine) as s:
        j = s.get(Job, jid)
        if j:
            j.status, j.result, j.updated_at = status, (result or "")[:4000], _now()
            s.add(j)
            s.commit()


def _loop():
    from . import chat  # late import to avoid import cycles
    while True:
        job = _claim_next()
        if not job:
            time.sleep(1.0)
            continue
        try:
            budget = Budget(max_usd=job["max_usd"], max_iterations=job["max_iterations"])
            final = chat.run_turn(job["session_id"], job["text"], budget=budget)
            _finish(job["id"], "done", final)
            # Proactive delivery: if this job's chat is Telegram-linked, push the result
            # to the phone (so a scheduled "every morning…" digest actually arrives).
            try:
                from . import telegram
                telegram.maybe_notify(job["session_id"], final)
            except Exception:
                pass
        except Exception as e:
            _finish(job["id"], "error", f"{type(e).__name__}: {e}")


def start_worker():
    """Idempotent: starts the background worker (also resumes jobs after a restart)."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    _recover_stale()   # re-queue jobs that were 'running' when the process last died
    threading.Thread(target=_loop, daemon=True).start()
