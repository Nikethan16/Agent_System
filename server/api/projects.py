"""projects.py — REST for Projects (group chats + shared knowledge)."""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from .. import projects

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateIn(BaseModel):
    name: str = "New project"


class UpdateIn(BaseModel):
    name: str | None = None
    instructions: str | None = None


@router.post("")
def create(body: CreateIn):
    return projects.create(body.name)


@router.get("")
def list_all():
    return projects.list_all()


@router.get("/{pid}")
def get(pid: str):
    p = projects.get(pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.patch("/{pid}")
def update(pid: str, body: UpdateIn):
    p = projects.update(pid, name=body.name, instructions=body.instructions)
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.delete("/{pid}")
def delete(pid: str):
    projects.delete(pid)
    return {"ok": True}


@router.get("/{pid}/files")
def files(pid: str):
    return projects.files(pid)


@router.post("/{pid}/files")
async def add_file(pid: str, file: UploadFile = File(...)):
    projects.add_file(pid, file.filename or "upload", await file.read())
    return {"ok": True, "files": projects.files(pid)}


@router.delete("/{pid}/files/{name}")
def remove_file(pid: str, name: str):
    projects.remove_file(pid, name)
    return {"ok": True, "files": projects.files(pid)}
