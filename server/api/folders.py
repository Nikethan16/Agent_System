"""folders.py — REST CRUD for folders (Project -> Folders -> Chats)."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db

router = APIRouter(prefix="/api/folders", tags=["folders"])


class CreateIn(BaseModel):
    project_id: str = ""
    name: str = "New folder"


class RenameIn(BaseModel):
    name: str


@router.post("")
def create(body: CreateIn):
    if not body.project_id:
        raise HTTPException(400, "folders must belong to a project")
    return db.create_folder(body.project_id, body.name)


@router.get("")
def list_all(project_id: Optional[str] = None):
    return db.list_folders(project_id)


@router.patch("/{folder_id}")
def rename(folder_id: str, body: RenameIn):
    f = db.rename_folder(folder_id, body.name)
    if not f:
        raise HTTPException(404, "folder not found")
    return f


@router.delete("/{folder_id}")
def delete(folder_id: str):
    if not db.delete_folder(folder_id):
        raise HTTPException(404, "folder not found")
    return {"ok": True}
