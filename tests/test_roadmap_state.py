"""Roadmap ("what's left") capture: new todos MERGE into the prior plan (update status by text,
append new), a no-todo turn PRESERVES the roadmap, and /todo lists the open items. Stubs
handle_task so it stays offline/deterministic."""
from core.llm import Budget
from server import chat, memory
from server.db import init_db, create_session

init_db()


def _run(monkeypatch, sid, todos, text="do stuff"):
    monkeypatch.setattr(memory, "_embed_model", lambda: None)
    monkeypatch.setattr(memory, "extract_facts", lambda *a, **k: [])   # no model calls

    def fake(task, budget=None, emit=None, **kw):
        emit({"type": "route", "tier": 2, "task_type": "frontend"})
        if todos is not None:
            emit({"type": "plan", "subtasks": [t["text"] for t in todos], "todos": todos})
        return "ok"

    monkeypatch.setattr(chat, "handle_task", fake)
    return chat.run_turn(sid, text, budget=Budget(), stream=False)


def test_roadmap_merges_and_preserves(monkeypatch):
    sid = create_session(title="rm").id
    scope = f"session:{sid}"
    _run(monkeypatch, sid, [{"text": "build login", "status": "in_progress"},
                            {"text": "write tests", "status": "pending"}])
    assert len(memory.get_state(scope)["plan"]) == 2

    # turn 2: login done + a new item — should merge, not replace
    _run(monkeypatch, sid, [{"text": "build login", "status": "done"},
                            {"text": "deploy", "status": "pending"}])
    texts = {p["text"]: p["status"] for p in memory.get_state(scope)["plan"]}
    assert texts["build login"] == "done"       # updated in place
    assert texts["write tests"] == "pending"    # preserved from turn 1
    assert texts["deploy"] == "pending"         # appended

    # turn 3: NO todos — roadmap must survive, next = first not-done
    _run(monkeypatch, sid, None)
    st = memory.get_state(scope)
    assert len(st["plan"]) == 3
    assert st["next"] == "write tests"


def test_todo_command_lists_open(monkeypatch):
    sid = create_session(title="rm2").id
    _run(monkeypatch, sid, [{"text": "alpha task", "status": "done"},
                            {"text": "beta task", "status": "pending"}])
    out = chat.run_turn(sid, "/todo", budget=Budget(), stream=False)
    assert "beta task" in out                    # open item listed
    assert "Completed so far: 1" in out


def test_todo_empty_when_no_roadmap():
    sid = create_session(title="rm3").id
    out = chat.run_turn(sid, "/todo", budget=Budget(), stream=False)
    assert "No roadmap captured" in out
