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


def list_all() -> list:
    with DBSession(engine) as s:
        return [p.model_dump() for p in s.exec(select(Project).order_by(Project.created_at.desc())).all()]


def get(pid: str):
    with DBSession(engine) as s:
        p = s.get(Project, pid)
        return p.model_dump() if p else None


def update(pid: str, name=None, instructions=None):
    with DBSession(engine) as s:
        p = s.get(Project, pid)
        if not p:
            return None
        if name is not None:
            p.name = name
        if instructions is not None:
            p.instructions = instructions
        s.add(p); s.commit(); s.refresh(p)
        return p.model_dump()


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
