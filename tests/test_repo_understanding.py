"""'Read & understand an existing repo/URL' must route to an agent that can FETCH the source
(repo-engineer), NOT the build path. A live failure (2026-07) saw 'understand github.com/x/y
and summarize it' get built by coder/frontend, which never read the repo and HALLUCINATED a
fictional app. This guards the deterministic route + the understand-first anti-fabrication skill."""
from types import SimpleNamespace

import core.orchestrator as o
from core import skills as sk


def test_shared_repo_understanding_routes_to_repo_engineer():
    for t in (
        "I'm sharing https://github.com/santifer/career-ops . FIRST understand what this "
        "application is and give me a brief summary. Do NOT propose changes.",
        "understand github.com/foo/bar and summarize it",
        "explain what the app at https://gitlab.com/x/y does",
    ):
        assert o._repo_understanding_agent(t) == "repo-engineer", t


def test_build_or_no_url_is_not_hijacked():
    # A build/modify request keeps normal routing even with a repo URL.
    assert o._repo_understanding_agent("build a new feature in github.com/foo/bar") == ""
    assert o._repo_understanding_agent("integrate github.com/foo/bar into our app") == ""
    # No URL -> not this route (a local codebase read goes through normal flow).
    assert o._repo_understanding_agent("write a fizzbuzz function with tests") == ""
    assert o._repo_understanding_agent("summarize this codebase") == ""


def test_understand_first_skill_selected_and_safe():
    sk.load()
    re_agent = SimpleNamespace(id="repo-engineer", capabilities=["git", "github"],
                               tools=["git_clone", "read_file", "run_bash"])
    picked = [s.name for s in sk.select(
        "understand github.com/santifer/career-ops and summarize what it is", agent=re_agent)]
    assert "understand-first" in picked
    # It's pure markdown guidance -> must not be flagged 'risky' (it names no dangerous calls).
    assert sk.scan("understand-first")["risk"] != "risky"


def test_understand_first_skill_has_antifabrication_guidance():
    s = sk.get("understand-first")
    body = (s.body or "").lower()
    assert "never describe what you haven't read" in body or "never describe" in body
    assert "stop and say so" in body or "couldn't" in body
