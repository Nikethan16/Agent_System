"""
db.py — SQLite persistence via SQLModel (sessions, messages, events).

One file (app.db), no separate server. Also owns per-session workspace paths so each
chat's files are isolated on disk.
"""
import os
import re
import json
import uuid
import shutil
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import event
from sqlmodel import SQLModel, Field, Session as DBSession, create_engine, select

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
# Always absolute+normalized so sandbox containment checks are reliable even if a
# user sets a relative DATA_DIR (e.g. one containing "..").
DATA_DIR = os.path.abspath(os.environ.get("DATA_DIR", os.path.join(_BASE, "data")))
WORKSPACES_DIR = os.path.join(DATA_DIR, "workspaces")
CHECKPOINTS_DIR = os.path.join(DATA_DIR, "checkpoints")
DB_PATH = os.environ.get("APP_DB", os.path.join(DATA_DIR, "app.db"))

os.makedirs(WORKSPACES_DIR, exist_ok=True)
os.makedirs(CHECKPOINTS_DIR, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _rec):
    # WAL allows concurrent readers + a writer; busy_timeout waits instead of erroring
    # when the background worker and the API touch the DB at the same time.
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InvalidId(ValueError):
    """A user-supplied id failed validation (path-traversal guard)."""


_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")   # uuid4().hex


def safe_id(value: str) -> str:
    """Validate a server-generated id (UUID hex) BEFORE using it in a filesystem
    path. Prevents path traversal / arbitrary-directory access (and the destructive
    rmtree in restore_checkpoint) via a crafted session/checkpoint/project id."""
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise InvalidId(f"invalid id: {value!r}")
    return value


class Session(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    title: str = "New chat"
    project_id: str = Field(default="", index=True)
    starred: bool = False
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class Message(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(index=True)
    role: str = "user"               # user | assistant
    content: str = ""
    cost: float = 0.0
    created_at: str = Field(default_factory=_now)


class Event(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(index=True)
    message_id: Optional[str] = Field(default=None, index=True)
    type: str = "thought"
    data: str = "{}"                 # JSON-encoded event payload
    created_at: str = Field(default_factory=_now)


class Checkpoint(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(index=True)
    label: str = ""
    created_at: str = Field(default_factory=_now)


def _migrate():
    """Additive migrations for columns introduced after a table already existed."""
    wanted = {
        "memory": [
            ("embedding", "TEXT DEFAULT ''"),
            ("scope", "TEXT DEFAULT ''"),       # global | project:<id> | session:<id>
            ("fact_key", "TEXT DEFAULT ''"),    # dedupe key for semantic facts
            ("updated_at", "TEXT DEFAULT ''"),  # facts/summaries change over time
        ],
        "session": [("project_id", "TEXT DEFAULT ''"), ("starred", "INTEGER DEFAULT 0")],
    }
    with engine.begin() as conn:
        for table, cols in wanted.items():
            existing = [r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")]
            if not existing:
                continue  # table will be created fresh (with the column) by create_all
            for name, decl in cols:
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init_db():
    from . import memory    # noqa: F401  (registers the Memory table)
    from . import jobs      # noqa: F401  (registers the Job table)
    from . import projects  # noqa: F401  (registers the Project table)
    from . import spend     # noqa: F401  (registers the Spend table)
    from . import benchmark  # noqa: F401  (registers the BenchmarkRun table)
    SQLModel.metadata.create_all(engine)
    _migrate()


def session_workspace(session_id: str) -> str:
    """Isolated on-disk folder for a chat's files/artifacts."""
    path = os.path.join(WORKSPACES_DIR, safe_id(session_id))
    os.makedirs(path, exist_ok=True)
    return path


# ---- small CRUD helpers -----------------------------------------------------
def create_session(title: str = "New chat", project_id: str = "") -> Session:
    with DBSession(engine) as s:
        obj = Session(title=title, project_id=project_id or "")
        s.add(obj)
        s.commit()
        s.refresh(obj)
        session_workspace(obj.id)
        return obj


def list_sessions(project_id: str = None) -> list:
    with DBSession(engine) as s:
        rows = s.exec(select(Session).order_by(Session.updated_at.desc())).all()
        out = [r.model_dump() for r in rows]
    if project_id is not None:
        out = [r for r in out if (r.get("project_id") or "") == project_id]
    out.sort(key=lambda r: (not r.get("starred"),))   # starred first (stable on updated_at)
    return out


def toggle_star(session_id: str):
    with DBSession(engine) as s:
        obj = s.get(Session, session_id)
        if not obj:
            return None
        obj.starred = not obj.starred
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj.model_dump()


def get_session(session_id: str):
    with DBSession(engine) as s:
        obj = s.get(Session, session_id)
        return obj.model_dump() if obj else None


def rename_session(session_id: str, title: str):
    with DBSession(engine) as s:
        obj = s.get(Session, session_id)
        if not obj:
            return None
        obj.title = title
        obj.updated_at = _now()
        s.add(obj)
        s.commit()
        s.refresh(obj)          # reload attrs expired by commit before dumping
        return obj.model_dump()


def delete_session(session_id: str):
    with DBSession(engine) as s:
        obj = s.get(Session, session_id)
        if obj:
            s.delete(obj)
            for m in s.exec(select(Message).where(Message.session_id == session_id)).all():
                s.delete(m)
            for e in s.exec(select(Event).where(Event.session_id == session_id)).all():
                s.delete(e)
            s.commit()


def touch_session(session_id: str):
    with DBSession(engine) as s:
        obj = s.get(Session, session_id)
        if obj:
            obj.updated_at = _now()
            s.add(obj)
            s.commit()


def add_message(session_id: str, role: str, content: str, cost: float = 0.0) -> str:
    with DBSession(engine) as s:
        m = Message(session_id=session_id, role=role, content=content, cost=cost)
        s.add(m)
        s.commit()
        s.refresh(m)
        return m.id


def truncate_messages(session_id: str, keep: int):
    """Keep the first `keep` messages of a session, delete the rest (for edit/branch)."""
    with DBSession(engine) as s:
        rows = s.exec(
            select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
        ).all()
        for m in rows[max(0, keep):]:
            s.delete(m)
        s.commit()


def get_messages(session_id: str) -> list:
    with DBSession(engine) as s:
        rows = s.exec(
            select(Message).where(Message.session_id == session_id)
            .order_by(Message.created_at)
        ).all()
        return [r.model_dump() for r in rows]


def add_event(session_id: str, ev: dict, message_id: str = None):
    with DBSession(engine) as s:
        s.add(Event(session_id=session_id, message_id=message_id,
                    type=ev.get("type", "event"), data=json.dumps(ev, default=str)))
        s.commit()


# ---- checkpoints (snapshot / rewind the session workspace) ------------------
def _cp_dir(session_id: str, checkpoint_id: str) -> str:
    return os.path.join(CHECKPOINTS_DIR, safe_id(session_id), safe_id(checkpoint_id))


# Keep only the most recent N checkpoints per session — each one is a full copy of
# the workspace, so unbounded snapshots grow disk without limit.
MAX_CHECKPOINTS = int(os.environ.get("MAX_CHECKPOINTS", "20"))


def _prune_checkpoints(session_id: str):
    cps = list_checkpoints(session_id)            # newest-first
    stale = cps[MAX_CHECKPOINTS:]
    if not stale:
        return
    with DBSession(engine) as s:
        for cp in stale:
            obj = s.get(Checkpoint, cp["id"])
            if obj:
                s.delete(obj)
            shutil.rmtree(_cp_dir(session_id, cp["id"]), ignore_errors=True)
        s.commit()


def create_checkpoint(session_id: str, label: str = "") -> str:
    """Snapshot the session workspace so the user can rewind to before this turn."""
    with DBSession(engine) as s:
        cp = Checkpoint(session_id=session_id, label=(label or "")[:140])
        s.add(cp)
        s.commit()
        s.refresh(cp)
        cid = cp.id
    src = session_workspace(session_id)
    dst = _cp_dir(session_id, cid)
    os.makedirs(dst, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    _prune_checkpoints(session_id)
    return cid


def latest_checkpoint_dir(session_id: str):
    """Path of the most recent checkpoint (the pre-last-turn snapshot), or None."""
    cps = list_checkpoints(session_id)
    return _cp_dir(session_id, cps[0]["id"]) if cps else None


def list_checkpoints(session_id: str) -> list:
    with DBSession(engine) as s:
        rows = s.exec(
            select(Checkpoint).where(Checkpoint.session_id == session_id)
            .order_by(Checkpoint.created_at.desc())
        ).all()
        return [r.model_dump() for r in rows]


def restore_checkpoint(session_id: str, checkpoint_id: str) -> bool:
    src = _cp_dir(session_id, checkpoint_id)
    if not os.path.isdir(src):
        return False
    ws = session_workspace(session_id)
    for n in os.listdir(ws):                      # wipe current workspace
        p = os.path.join(ws, n)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                os.remove(p)
            except OSError:
                pass
    shutil.copytree(src, ws, dirs_exist_ok=True)  # restore snapshot
    return True
