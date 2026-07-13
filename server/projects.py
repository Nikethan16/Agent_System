"""
projects.py — Projects (Claude-style): group chats under a project with shared
INSTRUCTIONS + KNOWLEDGE FILES that get injected as context into every chat in the
project. Files live under data/projects/<id>/.
"""
import os
import logging

from sqlmodel import SQLModel, Field, Session as DBSession, select

from .db import engine, _uuid, _now, DATA_DIR, safe_id

log = logging.getLogger(__name__)

PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)


class Project(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = "New project"
    instructions: str = ""          # custom guidance prepended to every chat in the project
    budget_usd: float = 0.0         # cumulative spend cap for this project (0 = unlimited)
    repo_url: str = ""              # if created from a git repo, its origin URL (for the repo panel)
    created_at: str = Field(default_factory=_now)


def _dir(pid: str) -> str:
    p = os.path.join(PROJECTS_DIR, safe_id(pid))
    os.makedirs(p, exist_ok=True)
    return p


def create(name: str = "New project") -> dict:
    with DBSession(engine) as s:
        p = Project(name=name)
        s.add(p); s.commit(); s.refresh(p)
        _dir(p.id)
        return p.model_dump()


def create_from_repo(name: str, url: str, branch: str = "") -> dict:
    """Create a project and clone `url` into its shared workspace, so every session in
    the project works on the real repo (the hosted equivalent of 'open a folder'). The
    project is created regardless; the clone result is returned under `clone` so the UI
    can surface a failure without losing the project."""
    from .db import project_workspace
    from tools import github as gh
    p = create(name or "New project")
    pid = p["id"]
    ws = project_workspace(pid)
    # Clone only into an EMPTY workspace (a fresh project) — never clobber existing files.
    if any(os.scandir(ws)):
        return {**p, "clone": {"ok": False, "message": "workspace is not empty — not cloning"}}
    ok, msg = gh.clone_into(url.strip(), ws, branch=branch.strip())
    if ok:
        with DBSession(engine) as s:
            row = s.get(Project, pid)
            if row:
                row.repo_url = url.strip()
                s.add(row); s.commit()
    return {**get(pid), "clone": {"ok": ok, "message": (msg or "")[:2000]}}


def list_all() -> list:
    with DBSession(engine) as s:
        return [p.model_dump() for p in s.exec(select(Project).order_by(Project.created_at.desc())).all()]


def get(pid: str):
    with DBSession(engine) as s:
        p = s.get(Project, pid)
        return p.model_dump() if p else None


def update(pid: str, name=None, instructions=None, budget_usd=None):
    with DBSession(engine) as s:
        p = s.get(Project, pid)
        if not p:
            return None
        if name is not None:
            p.name = name
        if instructions is not None:
            p.instructions = instructions
        if budget_usd is not None:
            try:
                p.budget_usd = max(0.0, float(budget_usd))
            except (TypeError, ValueError):
                pass
        s.add(p); s.commit(); s.refresh(p)
        return p.model_dump()


def budget_of(pid: str) -> float:
    """The project's spend cap (0 = unlimited). Safe on a missing project."""
    p = get(pid)
    return float(p.get("budget_usd", 0.0) or 0.0) if p else 0.0


def delete(pid: str):
    with DBSession(engine) as s:
        p = s.get(Project, pid)
        if p:
            s.delete(p); s.commit()


def files(pid: str) -> list:
    d = _dir(pid)
    return [{"name": n, "size": os.path.getsize(os.path.join(d, n))}
            for n in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, n))]


def add_file(pid: str, name: str, data: bytes):
    with open(os.path.join(_dir(pid), os.path.basename(name)), "wb") as f:
        f.write(data)


def remove_file(pid: str, name: str):
    p = os.path.join(_dir(pid), os.path.basename(name))
    if os.path.isfile(p):
        os.remove(p)


def repo_info(pid: str) -> dict:
    """Git status of the project's workspace, for the repo panel: branch, changed files,
    and recent commits. {repo: False} when the workspace isn't a git repo."""
    from .db import project_workspace
    from tools import github as gh
    ws = project_workspace(pid)
    if not os.path.isdir(os.path.join(ws, ".git")):
        return {"repo": False}

    def g(args):
        rc, out, err = gh._git(args, cwd=ws)
        return (out if rc == 0 else "").strip()

    changed = [ln for ln in g(["status", "--porcelain"]).splitlines() if ln.strip()]
    return {
        "repo": True,
        "url": (get(pid) or {}).get("repo_url", ""),
        "branch": g(["rev-parse", "--abbrev-ref", "HEAD"]) or "(detached)",
        "changed": len(changed),
        "files": changed[:100],                       # porcelain lines (status + path)
        "recent": g(["log", "--oneline", "-8"]).splitlines()[:8],
    }


def file_texts(pid: str) -> dict:
    """Per-file raw text of a project's knowledge files (for RAG indexing)."""
    out = {}
    if not pid:
        return out
    d = _dir(pid)
    for n in sorted(os.listdir(d)):
        full = os.path.join(d, n)
        if not os.path.isfile(full):
            continue
        try:
            if n.lower().endswith(".pdf"):
                from pypdf import PdfReader
                out[n] = "\n".join((pg.extract_text() or "") for pg in PdfReader(full).pages)
            else:
                with open(full, encoding="utf-8", errors="replace") as f:
                    out[n] = f.read()
        except Exception as e:
            log.warning("skipping unreadable project file %s: %s", full, e)
    return out


def context(pid: str, limit_per_file: int = 4000) -> str:
    """The project's instructions + knowledge file texts, for injection into chats."""
    if not pid:
        return ""
    p = get(pid)
    if not p:
        return ""
    parts = []
    if p.get("instructions"):
        parts.append("Project instructions:\n" + p["instructions"])
    d = _dir(pid)
    for n in sorted(os.listdir(d)):
        full = os.path.join(d, n)
        if not os.path.isfile(full):
            continue
        try:
            if n.lower().endswith(".pdf"):
                from pypdf import PdfReader
                txt = "\n".join((pg.extract_text() or "") for pg in PdfReader(full).pages)
            else:
                with open(full, encoding="utf-8", errors="replace") as f:
                    txt = f.read()
            parts.append(f"Project knowledge '{n}':\n{txt[:limit_per_file]}")
        except Exception as e:
            log.warning("skipping unreadable project file %s: %s", full, e)
    return ("Project context (shared across this project's chats):\n\n" + "\n\n".join(parts)) if parts else ""
