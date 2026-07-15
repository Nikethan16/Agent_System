"""sessions.py — REST CRUD for chat sessions."""
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import db
from .. import trace

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateIn(BaseModel):
    title: str = "New chat"
    project_id: str = ""


class RenameIn(BaseModel):
    title: str


class MoveIn(BaseModel):
    project_id: Optional[str] = None
    folder_id: Optional[str] = None


@router.post("")
def create(body: CreateIn):
    return db.create_session(body.title, body.project_id).model_dump()


@router.get("")
def list_all(project_id: Optional[str] = None):
    return db.list_sessions(project_id)


@router.get("/{session_id}")
def get_one(session_id: str):
    s = db.get_session(session_id)
    if not s:
        raise HTTPException(404, "session not found")
    return s


@router.patch("/{session_id}")
def rename(session_id: str, body: RenameIn):
    s = db.rename_session(session_id, body.title)
    if not s:
        raise HTTPException(404, "session not found")
    return s


@router.delete("/{session_id}")
def delete(session_id: str):
    if not db.get_session(session_id):
        raise HTTPException(404, "session not found")
    db.delete_session(session_id)
    return {"ok": True}


@router.post("/{session_id}/move")
def move(session_id: str, body: MoveIn):
    s = db.move_session(session_id, project_id=body.project_id, folder_id=body.folder_id)
    if not s:
        raise HTTPException(404, "session not found")
    return s


@router.post("/{session_id}/star")
def star(session_id: str):
    s = db.toggle_star(session_id)
    if not s:
        raise HTTPException(404, "session not found")
    return s


class FeedbackIn(BaseModel):
    value: Literal["up", "down"]
    note: str = ""


@router.post("/{session_id}/feedback")
def feedback(session_id: str, body: FeedbackIn):
    if not db.get_session(session_id):
        raise HTTPException(404, "session not found")
    trace.trace(session_id, {"type": "feedback", "value": body.value, "note": body.note})
    return {"ok": True}


@router.get("/{session_id}/messages")
def messages(session_id: str):
    return db.get_messages(session_id)


@router.get("/{session_id}/checkpoints")
def checkpoints(session_id: str):
    return db.list_checkpoints(session_id)


class RestoreIn(BaseModel):
    checkpoint_id: str


@router.post("/{session_id}/restore")
def restore(session_id: str, body: RestoreIn):
    if not db.restore_checkpoint(session_id, body.checkpoint_id):
        raise HTTPException(404, "checkpoint not found")
    return {"ok": True}


class TruncateIn(BaseModel):
    keep: int = Field(ge=0)


@router.post("/{session_id}/truncate")
def truncate(session_id: str, body: TruncateIn):
    if not db.get_session(session_id):
        raise HTTPException(404, "session not found")
    db.truncate_messages(session_id, body.keep)
    return {"ok": True}
