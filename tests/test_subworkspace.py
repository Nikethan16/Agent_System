"""Tests for the fresh-build slug heuristic (orch #6, core/tools.py).

Only the pure helper is tested here; the binding is gated OFF by default in
server/chat.py behind AGENT_TASK_SUBWORKSPACE.
"""
from core.tools import fresh_build_slug


def test_fresh_build_detected():
    slug = fresh_build_slug("build a todo app with a REST API")
    assert slug and slug.startswith("proj_")
    assert "todo" in slug


def test_create_website_detected():
    assert fresh_build_slug("create a landing page for my startup")


def test_followup_not_detected():
    assert fresh_build_slug("add a delete button to the app") is None
    assert fresh_build_slug("continue building the project") is None
    assert fresh_build_slug("fix the bug in the existing API") is None


def test_non_build_not_detected():
    assert fresh_build_slug("what is the capital of France?") is None
    assert fresh_build_slug("explain how recursion works") is None


def test_slug_is_bounded_and_safe():
    slug = fresh_build_slug("build a really really really long named dashboard service thing tool")
    assert slug and len(slug) <= 48
    # no spaces / path separators
    assert " " not in slug and "/" not in slug and "\\" not in slug
