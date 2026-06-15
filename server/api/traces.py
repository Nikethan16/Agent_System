"""traces.py — REST for a session's local observability trace.

Surfaces the always-on JSONL trace (data/traces/<id>.jsonl) as a reconstructed
span tree so the UI can show what each run actually did — which subagents ran,
which tools fired, and the cost/tokens/duration per step — without needing
Langfuse. Read-only; the tree is rebuilt from the flat event log at request time.
"""
from fastapi import APIRouter, HTTPException

from .. import trace
from .. import db

router = APIRouter(prefix="/api/traces", tags=["traces"])


@router.get("/{session_id}")
def get_trace(session_id: str):
    """The span tree + raw event list for a session's run trace."""
    try:
        db.safe_id(session_id)
    except db.InvalidId:
        raise HTTPException(400, "invalid session id")
    tree = trace.build_tree(session_id)
    events = trace.load_trace(session_id)
    return {"session_id": session_id, "tree": tree["root"],
            "totals": tree["totals"], "events": events}
