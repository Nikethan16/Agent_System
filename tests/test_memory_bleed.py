"""Regression: episodic "memory bleed".

A just-finished UNRELATED chat (e.g. a habit-tracker build) must not be recalled into a
fresh, different question (e.g. "open this xlsx"). An embedding match can rate two unrelated
"build X" tasks as similar, and a weak lexical match can fire on a couple of incidental shared
words — so recall applies a DISTINCTIVE-word gate (server/memory._relevant). Also: an answer
the QA critic failed must not be stored (a wrong answer that gets recalled + parroted later).

Mirrors scenario F in scripts/e2e_local.py (the off-topic detector).
"""
from sqlmodel import Session as DBSession, select

from server import memory
from server.db import engine, init_db

init_db()   # ensure the Memory table exists in the throwaway test DB


_HABIT = ("Request: Build a habit tracker as a single self-contained index.html file "
          "(vanilla JS, localStorage) with streak counters.\n"
          "Outcome: Perfect! The habit tracker is fully functional. Open index.html to use it.")
_XLSX_Q = "Open the attached file quarterly_numbers.xlsx and summarize it."


def _clear_turns():
    with DBSession(engine) as s:
        for m in s.exec(select(memory.Memory)).all():
            s.delete(m)
        s.commit()


# ---- the pure gate (backend-agnostic — the real guard) ---------------------
def test_relevant_gate_blocks_unrelated():
    q = set(memory._tokens(_XLSX_Q))
    # shares only generic boilerplate ("open"/"file") — no distinctive subject word
    assert not memory._relevant(q, _HABIT)


def test_relevant_gate_allows_related():
    q = set(memory._tokens("what were the quarterly numbers in the xlsx"))
    note = "Request: analyze quarterly_numbers.xlsx.\nOutcome: Q1 revenue 4.2M, Q2 5.1M."
    assert memory._relevant(q, note)


def test_relevant_gate_disabled_via_env(monkeypatch):
    monkeypatch.setattr(memory, "_MIN_DISTINCTIVE", 0)
    assert memory._relevant(set(memory._tokens(_XLSX_Q)), _HABIT)  # gate off → passes


# ---- write-time self-consistency guard (don't store a bled/parroted answer) ----
def test_off_topic_answer_is_not_self_consistent():
    # request about an xlsx, answer about a habit tracker → off-topic, must not be stored
    answer = ("I've successfully created a fully functional Habit Tracker application with add, "
              "streak, delete and a weekly grid. " * 4)
    assert not memory.is_self_consistent(_XLSX_Q, answer)


def test_on_topic_answer_is_self_consistent():
    answer = ("The quarterly_numbers.xlsx spreadsheet reports total revenue and per-region "
              "numbers for the quarter; East leads. " * 3)
    assert memory.is_self_consistent(_XLSX_Q, answer)


def test_short_answer_always_consistent():
    assert memory.is_self_consistent("what is the capital of France", "Paris.")


# ---- end-to-end recall (force offline lexical path, deterministic) ---------
def test_recall_does_not_bleed_unrelated_chat(monkeypatch):
    monkeypatch.setattr(memory, "_embed_model", lambda: None)   # offline lexical path
    _clear_turns()
    memory.remember(_HABIT, session_id="s1", kind="turn", scope="session:s1")
    hits = memory.recall(_XLSX_Q, exclude_session="s2")
    assert all("habit tracker" not in h.lower() for h in hits), hits


def test_recall_still_returns_related_chat(monkeypatch):
    monkeypatch.setattr(memory, "_embed_model", lambda: None)
    _clear_turns()
    memory.remember("Request: analyze quarterly_numbers.xlsx.\nOutcome: Q1 revenue 4.2M.",
                    session_id="s1", kind="turn", scope="session:s1")
    hits = memory.recall("what were the quarterly numbers", exclude_session="s2")
    assert any("quarterly" in h.lower() for h in hits), hits
