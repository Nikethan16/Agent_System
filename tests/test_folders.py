"""Folders (Project -> Folders -> Chats) + move-session logic (server/db.py).

Self-isolating: swaps db.engine to a temp SQLite file so it never touches the real
app.db (unlike the older project/spend tests, which seed into the shared DB).
"""
import os
import tempfile

import pytest
from sqlmodel import Session as DBSession, SQLModel, create_engine

from server import db


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch):
    path = os.path.join(tempfile.mkdtemp(), "folders_test.db")
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db, "engine", eng)
    SQLModel.metadata.create_all(eng)
    yield


def _mk_session(title, project_id):
    with DBSession(db.engine) as s:
        obj = db.Session(title=title, project_id=project_id)
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj.id


PID = "a" * 32


def test_create_and_list_folder():
    f = db.create_folder(PID, "Phase 1")
    assert f["project_id"] == PID and f["name"] == "Phase 1"
    assert any(x["id"] == f["id"] for x in db.list_folders(PID))
    assert db.list_folders("other") == []


def test_move_session_into_and_out_of_folder():
    sid = _mk_session("chat", PID)
    f = db.create_folder(PID, "Phase 1")
    r = db.move_session(sid, project_id=PID, folder_id=f["id"])
    assert r["folder_id"] == f["id"] and r["project_id"] == PID
    # moving to no project must clear the folder (a folder belongs to a project)
    r = db.move_session(sid, project_id="", folder_id=f["id"])
    assert r["project_id"] == "" and r["folder_id"] == ""


def test_cross_project_folder_is_rejected():
    sid = _mk_session("chat", "b" * 32)
    f = db.create_folder(PID, "Phase 1")   # folder belongs to PID, not to 'b'*32
    r = db.move_session(sid, project_id="b" * 32, folder_id=f["id"])
    assert r["folder_id"] == ""            # stale cross-project folder can't attach


def test_delete_folder_cascades_chats_to_root():
    sid = _mk_session("chat", PID)
    f = db.create_folder(PID, "Phase 1")
    db.move_session(sid, project_id=PID, folder_id=f["id"])
    assert db.delete_folder(f["id"]) is True
    assert db.list_folders(PID) == []
    assert {x["id"]: x for x in db.list_sessions(PID)}[sid]["folder_id"] == ""


def test_rename_folder():
    f = db.create_folder(PID, "old")
    r = db.rename_folder(f["id"], "new")
    assert r["name"] == "new"
    assert db.rename_folder("nope", "x") is None
