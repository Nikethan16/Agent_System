"""
runs.py (API) — reattach to in-flight runs + answer approvals out-of-band.

These endpoints make a run survive a browser disconnect:
  * GET  /api/sessions/{id}/active-run  — is a run in progress, and what approvals are
                                          waiting? (the UI calls this on (re)load)
  * GET  /api/sessions/{id}/approvals   — pending approval requests for a session
  * POST /api/approvals/{req_id}/resolve — approve/deny later, from any client

Resolution goes through approvals.resolve(), which finds the live waiting run anywhere in
the process (the originating socket, a second tab, or Telegram) and unblocks it.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import runs
from .. import approvals

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/sessions/{session_id}/active-run")
def active_run(session_id: str):
    return {"run": runs.active_run(session_id),
            "pending": runs.pending_approvals(session_id)}


@router.get("/sessions/{session_id}/approvals")
def session_approvals(session_id: str):
    return {"pending": runs.pending_approvals(session_id)}


class ResolveIn(BaseModel):
    allowed: bool
    reason: str = ""


@router.post("/approvals/{req_id}/resolve")
def resolve_approval(req_id: str, body: ResolveIn):
    rec = runs.get_approval(req_id)
    if not rec:
        raise HTTPException(404, "no such approval")
    if rec["status"] != "pending":
        return {"ok": False, "already": rec["status"]}
    # Unblock the waiting run if it's still alive; otherwise just record the verdict.
    live = approvals.resolve(req_id, body.allowed, body.reason, decided_by="user")
    return {"ok": True, "live": live, "status": "approved" if body.allowed else "denied"}
