"""Tests for skill gating (orch #5): auto-matching can be disabled for trivial
tier-1 tasks, while explicit names still load."""
from core import skills as sk


def test_auto_false_returns_nothing_without_names():
    # A task that WOULD normally match a skill returns none when auto is off.
    assert sk.select("write a python function with tests") != []   # baseline: matches
    assert sk.select("write a python function with tests", auto=False) == []


def test_auto_false_still_honors_explicit_names():
    chosen = sk.select("anything at all", names=["pdf"], auto=False)
    assert any(s.name == "pdf" for s in chosen)


def test_auto_true_is_default_behavior_unchanged():
    # deck still maps to pptx with auto on (default)
    assert any(s.name == "pptx" for s in sk.select("make a slide deck for Q3"))
