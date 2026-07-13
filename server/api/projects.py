"""projects.py — REST for Projects (group chats + shared knowledge)."""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from .. import projects
from .. import spend

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateIn(BaseModel):
    name: str = "New project"
    repo_url: str = ""      # optional: clone this git repo into the project workspace
    branch: str = ""        # optional branch to check out on clone
    local_path: str = ""    # optional: bind to a real local folder (local mode only)


class UpdateIn(BaseModel):
    name: str | None = None
    instructions: str | None = None
    budget_usd: float | None = None


@router.post("")
def create(body: CreateIn):
    if body.local_path.strip():
        r = projects.create_local(body.name, body.local_path)
        if r.get("error"):
            raise HTTPException(400, r["error"])
        return r
    if body.repo_url.strip():
        return projects.create_from_repo(body.name, body.repo_url, body.branch)
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
    p = projects.update(pid, name=body.name, instructions=body.instructions,
                        budget_usd=body.budget_usd)
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.get("/{pid}/spend")
def project_spend(pid: str):
    """Cumulative spend for this project + its budget cap (for the dashboard)."""
    p = projects.get(pid)
    if not p:
        raise HTTPException(404, "project not found")
    return spend.project_status(pid, projects.budget_of(pid))


@router.delete("/{pid}")
def delete(pid: str):
    projects.delete(pid)
    return {"ok": True}


@router.get("/{pid}/repo")
def repo(pid: str):
    """Git status of the project's workspace (branch / changed files / recent commits)."""
    if not projects.get(pid):
        raise HTTPException(404, "project not found")
    return projects.repo_info(pid)


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
