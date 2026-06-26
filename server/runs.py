"""
runs.py — persistence for active runs + human approval requests (the "unattended runs"
feature).

Two SQLite-backed tables so a run no longer lives only in WebSocket memory:
  * RunState   — one row per turn (running/done/error/stopped) so the UI can show "a run
                 is in progress" after a reload, and reattach to it.
  * Approval   — one row per escalated action that needs a human. The request SURVIVES a
                 browser disconnect: it can be answered later from any client (the UI on
                 reconnect or a second tab), instead of being lost when the
                 socket that raised it goes away.

This module owns only the data. The live wiring (block the worker thread, unblock it when
an answer arrives from anywhere in the process) is in server/approvals.py.
"""
from typing import Optional

from sqlmodel import SQLModel, Field, Session as DBSession, select

from .db import engine, _uuid, _now


class RunState(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(index=True)
    status: str = "running"            # running | done | error | stopped
    text: str = ""                     # the user's request (for display on reattach)
    started_at: str = Field(default_factory=_now)
    finished_at: str = ""
    cost: float = 0.0


class Approval(SQLModel, table=True):
    id: str = Field(primary_key=True)  # the broker's req_id (uuid hex) — set explicitly
    session_id: str = Field(default="", index=True)
    run_id: str = Field(default="", index=True)
    tool: str = ""
    args: str = "{}"                   # JSON-encoded
    risk: str = ""
    reason: str = ""
    manager_reason: str = ""
    status: str = "pending"            # pending | approved | denied | timeout
    decided_by: str = ""               # who answered (user / timeout)
    created_at: str = Field(default_factory=_now)
    resolved_at: str = ""


# ---- run state --------------------------------------------------------------
def start_run(session_id: str, text: str) -> str:
    with DBSession(engine) as s:
        r = RunState(session_id=session_id, text=(text or "")[:500])
        s.add(r)
        s.commit()
        s.refresh(r)
        return r.id


def finish_run(run_id: str, status: str = "done", cost: float = 0.0) -> None:
    if not run_id:
        return
    with DBSession(engine) as s:
        r = s.get(RunState, run_id)
        if r and r.status == "running":
            r.status = status
            r.finished_at = _now()
            r.cost = round(cost or 0.0, 6)
            s.add(r)
            s.commit()


def active_run(session_id: str) -> Optional[dict]:
    """The most recent still-running run for a session (or None)."""
    with DBSession(engine) as s:
        rows = s.exec(
            select(RunState).where(RunState.session_id == session_id,
                                   RunState.status == "running")
            .order_by(RunState.started_at.desc())
        ).all()
        return rows[0].model_dump() if rows else None


def mark_stale_running_done() -> int:
    """On server startup, any run still marked 'running' is orphaned (its worker thread
    died with the previous process). Mark them 'error' so the UI doesn't show a ghost run."""
    n = 0
    with DBSession(engine) as s:
        for r in s.exec(select(RunState).where(RunState.status == "running")).all():
            r.status = "error"
            r.finished_at = _now()
            s.add(r)
            n += 1
        s.commit()
    return n


# ---- approvals --------------------------------------------------------------
def create_approval(req_id: str, session_id: str, run_id: str, tool: str, args: str,
                    risk: str, reason: str, manager_reason: str) -> None:
    with DBSession(engine) as s:
        s.add(Approval(id=req_id, session_id=session_id or "", run_id=run_id or "",
                       tool=tool, args=args, risk=risk, reason=reason,
                       manager_reason=manager_reason))
        s.commit()


def resolve_approval(req_id: str, status: str, decided_by: str = "") -> bool:
    with DBSession(engine) as s:
        a = s.get(Approval, req_id)
        if not a or a.status != "pending":
            return False
        a.status = status
        a.decided_by = decided_by
        a.resolved_at = _now()
        s.add(a)
        s.commit()
        return True


def get_approval(req_id: str) -> Optional[dict]:
    with DBSession(engine) as s:
        a = s.get(Approval, req_id)
        return a.model_dump() if a else None


def pending_approvals(session_id: str = None) -> list:
    with DBSession(engine) as s:
        q = select(Approval).where(Approval.status == "pending")
        if session_id is not None:
            q = q.where(Approval.session_id == session_id)
        rows = s.exec(q.order_by(Approval.created_at)).all()
        return [r.model_dump() for r in rows]
