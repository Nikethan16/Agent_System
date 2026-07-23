"""Fact-extraction quality: a one-off task/command must not trigger fact extraction (the
habit-tracker bug), and a genuine self-introduction must. The signal gate also skips the extra
model call on task turns (a per-turn cost saving)."""
from server import memory
from server.db import init_db

init_db()


def test_task_command_extracts_nothing_offline():
    # No first-person/preference signal → returns [] WITHOUT any model call (safe offline).
    assert memory.extract_facts("Build a habit tracker with 7-day checkboxes and streaks") == []
    assert memory.extract_facts("Fix the failing tests in expenses.py and run the suite") == []


def test_signal_matches_self_intro_not_task():
    assert memory._FACT_SIGNAL.search("I'm Priya and I work mainly in Python")
    assert memory._FACT_SIGNAL.search("From now on always use tabs, not spaces")
    assert not memory._FACT_SIGNAL.search("Build a habit tracker application")
    assert not memory._FACT_SIGNAL.search("Summarize the attached quarterly report")
