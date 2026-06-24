"""schedules.py — REST for scheduled tasks (create / list / toggle / run-now / delete).

A schedule runs a saved prompt in a chosen chat on a recurring (or one-off) basis via
the persistent job queue. See server/scheduler.py for the schedule kinds + specs.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import scheduler

router = APIRouter(prefix="/api/schedules", tags=["schedules"])

_KINDS = {"once", "interval", "daily", "weekly"}


class ScheduleIn(BaseModel):
    session_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=8000)
    kind: str = "once"
    spec: str = ""
    max_usd: float = 0.5
    max_iterations: int = 20


@router.get("")
def list_schedules(session_id: Optional[str] = None):
    """Each schedule, enriched with its last run's outcome (status + a short result
    snippet) joined from the job queue via last_job_id — so the UI can show whether the
    most recent run succeeded, failed, or is still running without a second request."""
    from .. import jobs
    rows = scheduler.list_all(session_id)
    for r in rows:
        jid = r.get("last_job_id")
        job = jobs.get_job(jid) if jid else None
        if job:
            r["last_status"] = job.get("status")
            r["last_result"] = (job.get("result") or "")[:200]
        else:
            r["last_status"] = None
            r["last_result"] = ""
    return rows


@router.post("")
def create_schedule(body: ScheduleIn):
    if body.kind not in _KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(_KINDS)}")
    sch = scheduler.create(body.session_id, body.text, body.kind, body.spec,
                           body.max_usd, body.max_iterations)
    if not sch.get("next_run_at") and body.kind != "once":
        raise HTTPException(400, "could not compute a next run time from that spec")
    return sch


@router.post("/{sid}/toggle")
def toggle_schedule(sid: str):
    out = scheduler.set_enabled(sid, not (scheduler.get(sid) or {}).get("enabled", False))
    if out is None:
        raise HTTPException(404, "schedule not found")
    return out


@router.post("/{sid}/run")
def run_now(sid: str):
    out = scheduler.run_now(sid)
    if out is None:
        raise HTTPException(404, "schedule not found")
    if out.get("error"):
        raise HTTPException(409, out["error"])
    return out


@router.delete("/{sid}")
def delete_schedule(sid: str):
    if not scheduler.delete(sid):
        raise HTTPException(404, "schedule not found")
    return {"ok": True}
