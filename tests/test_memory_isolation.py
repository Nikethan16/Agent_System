"""Memory isolation (owner's chosen model: standalone chats are isolated; same-project chats
share). Episodic recall is HARD-LIMITED to the run's scope, so nothing bleeds between unrelated
chats or across projects. Regression for the cross-chat/cross-project bleed."""
from sqlmodel import Session as DBSession, select

from server import memory
from server.db import engine, init_db

init_db()


def _clear():
    with DBSession(engine) as s:
        for m in s.exec(select(memory.Memory)).all():
            s.delete(m)
        s.commit()


def test_recall_limited_to_its_project(monkeypatch):
    monkeypatch.setattr(memory, "_embed_model", lambda: None)
    _clear()
    memory.remember("Request: analyze widget sales quarterly\nOutcome: revenue climbing",
                    session_id="s1", kind="turn", scope="project:A")
    memory.remember("Request: analyze widget sales quarterly\nOutcome: SECRET other-project data",
                    session_id="s2", kind="turn", scope="project:B")
    hits = memory.recall("widget sales quarterly numbers", scopes=["project:A"],
                         exclude_session="cur")
    assert hits                                             # project A's own note is found
    assert all("SECRET other-project" not in h for h in hits)   # project B never leaks


def test_standalone_chat_recalls_nothing_from_other_chats(monkeypatch):
    monkeypatch.setattr(memory, "_embed_model", lambda: None)
    _clear()
    memory.remember("Request: build a widget dashboard\nOutcome: dashboard finished",
                    session_id="chatX", kind="turn", scope="session:chatX")
    # a DIFFERENT standalone chat asks something closely related
    hits = memory.recall("build a widget dashboard", scopes=["session:chatY"],
                         exclude_session="chatY")
    assert hits == []                                      # chatY is isolated from chatX


def test_unscoped_recall_still_searches_everything(monkeypatch):
    # Back-compat: without a scopes filter, recall behaves as before (global search).
    monkeypatch.setattr(memory, "_embed_model", lambda: None)
    _clear()
    memory.remember("Request: analyze widget sales quarterly\nOutcome: revenue climbing",
                    session_id="s1", kind="turn", scope="project:A")
    hits = memory.recall("widget sales quarterly", exclude_session="cur")   # no scopes=
    assert hits
