"""Integration: the chat write-path (server/chat.run_turn) + episodic memory + db.

Exercises the "don't store a QA-failed answer" guard end-to-end by stubbing the pipeline
(core.orchestrator.handle_task) so the test stays fully offline/deterministic — no model
calls. Complements tests/test_memory_bleed.py (which unit-tests the recall gate).
"""
from sqlmodel import Session as DBSession, select

from core.llm import Budget
from server import chat, memory, db
from server.db import engine, init_db, create_session

init_db()


def _stored_turns(sid: str):
    with DBSession(engine) as s:
        return [m for m in s.exec(select(memory.Memory)).all()
                if m.kind == "turn" and m.session_id == sid]


def _run(monkeypatch, critic_passed):
    """Run one turn whose stubbed pipeline emits a route(tier1) + a critic verdict."""
    monkeypatch.setattr(memory, "_embed_model", lambda: None)   # offline (no embed calls)

    def fake_handle_task(task, budget=None, emit=None, **kw):
        emit({"type": "route", "tier": 1, "task_type": "chat"})
        if critic_passed is not None:
            emit({"type": "critic", "passed": critic_passed, "summary": "verdict"})
        return "Answer about quarterly widget revenue figures."

    monkeypatch.setattr(chat, "handle_task", fake_handle_task)
    sid = create_session(title="integ").id
    chat.run_turn(sid, "Summarize the quarterly widget revenue please.",
                  budget=Budget(), stream=False)
    return sid


def test_failed_critic_answer_is_not_stored(monkeypatch):
    sid = _run(monkeypatch, critic_passed=False)
    assert _stored_turns(sid) == []          # QA-failed answer must NOT pollute memory


def test_passing_answer_is_stored(monkeypatch):
    sid = _run(monkeypatch, critic_passed=True)
    assert len(_stored_turns(sid)) == 1       # good answer IS remembered


def test_no_critic_still_stored(monkeypatch):
    # Most turns run no critic at all — those must still be remembered (backward compat).
    sid = _run(monkeypatch, critic_passed=None)
    assert len(_stored_turns(sid)) == 1


def test_facts_scoped_to_session_not_global(monkeypatch):
    """The real memory-bleed root cause: a standalone chat must extract facts into its OWN
    scope, never 'global' (global facts inject into every session and cross-contaminate)."""
    seen = {}
    monkeypatch.setattr(memory, "_embed_model", lambda: None)
    monkeypatch.setattr(memory, "extract_facts",
                        lambda text, scope="global", budget=None: seen.setdefault("scope", scope))

    def fake_handle_task(task, budget=None, emit=None, **kw):
        emit({"type": "route", "tier": 2, "task_type": "frontend"})   # tier!=1 → facts run
        return "Built the requested thing."

    monkeypatch.setattr(chat, "handle_task", fake_handle_task)
    sid = create_session(title="integ").id            # standalone (no project)
    chat.run_turn(sid, "Build a small widget.", budget=Budget(), stream=False)
    assert seen.get("scope") == f"session:{sid}"       # scoped to THIS session, not 'global'


# ---- /clear and /compact built-in commands ---------------------------------
def test_clear_command_resets_context_and_memory(monkeypatch):
    monkeypatch.setattr(memory, "_embed_model", lambda: None)
    sid = create_session(title="c").id
    memory.remember(f"Request: earlier\nOutcome: did stuff", session_id=sid,
                    kind="turn", scope=f"session:{sid}")
    memory.set_summary(sid, "we did earlier things")
    out = chat.run_turn(sid, "/clear", budget=Budget(), stream=False)
    assert "cleared" in out.lower()
    assert db.context_reset_of(sid)                    # boundary set
    assert memory.get_summary(sid) == ""               # summary forgotten
    from sqlmodel import select
    from server.db import engine as _eng
    from server.db import Session as _S  # noqa
    from sqlmodel import Session as DBS
    with DBS(_eng) as s:
        turns = [m for m in s.exec(select(memory.Memory)).all()
                 if m.kind == "turn" and m.session_id == sid]
    assert turns == []                                 # this chat's episodic notes gone


def test_rule_proposal_scoped_to_project_not_global(monkeypatch):
    """Regression: propose_rule must get the run's own scope, not a hardcoded 'global' —
    otherwise a rule learned in one project bleeds into every other project's chats
    (the same class of bug the fact-scoping fix addressed, via the rules door instead)."""
    seen = {}
    monkeypatch.setattr(memory, "_embed_model", lambda: None)
    monkeypatch.setattr(memory, "propose_rule",
                        lambda task, result, scope="global", budget=None: seen.setdefault("scope", scope))

    def fake_handle_task(task, budget=None, emit=None, **kw):
        emit({"type": "route", "tier": 3, "task_type": "coding"})   # tier>=3 → rule proposal runs
        return "Built the requested thing."

    monkeypatch.setattr(chat, "handle_task", fake_handle_task)
    pid = "a" * 32   # a valid-looking project id (session_workspace requires uuid4().hex)
    sid = create_session(title="proj-chat", project_id=pid).id
    chat.run_turn(sid, "Add a feature to the project.", budget=Budget(), stream=False)
    assert seen.get("scope") == f"project:{pid}"       # scoped to the project, never 'global'


def test_active_rule_from_one_project_not_seen_by_another(monkeypatch):
    """End-to-end (storage layer): a rule approved under project A must not be injected
    into project B's chats via get_active_rules."""
    rid = memory.add_rule("run tests before declaring done", scope="project:A", proposed=True)
    memory.approve_rule(rid)
    assert "run tests before declaring done" in memory.get_active_rules(["global", "project:A"])
    assert "run tests before declaring done" not in memory.get_active_rules(["global", "project:B"])


def test_compact_command_sets_boundary_and_summary(monkeypatch):
    monkeypatch.setattr(memory, "update_summary",
                        lambda sid, msgs, budget=None: memory.set_summary(sid, "compact summary"))
    sid = create_session(title="c2").id
    db.add_message(sid, "user", "do thing one")
    db.add_message(sid, "assistant", "done one")
    out = chat.run_turn(sid, "/compact", budget=Budget(), stream=False)
    assert "compact" in out.lower()
    assert db.context_reset_of(sid)                    # fresh boundary
    assert memory.get_summary(sid) == "compact summary"
