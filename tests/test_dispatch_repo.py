"""Explicit git-repo tasks must route to repo-engineer DETERMINISTICALLY.

Live e2e (2026-07, deployed VM): the LLM dispatcher picked `frontend` for "clone this
GitHub repo and summarize it" — frontend has no git tools, so the run dead-ended trying
`git clone` in the network-less bash sandbox. A github.com URL / clone / PR verb is not
ambiguous; it must never reach the model vote or an incomplete keyword table.
"""
from core import agents as team


REPO_TASKS = [
    "Clone the public GitHub repo https://github.com/octocat/Hello-World.git and tell me "
    "how many files it has, what the README says, and the last commit message.",
    "git clone https://gitlab.com/x/y and run the tests",
    "Work on https://github.com/a/b: fix the bug in utils.py and open a pull request",
    "clone the repo and summarize its structure",
    "make the change on a branch and create a pull request into main",
]

NON_REPO_TASKS = [
    "build a calculator web app",                      # frontend
    "write a python function that parses dates",       # coder
    "explain what a monorepo is",                      # general (no URL/clone/PR verb)
]


def test_select_agent_routes_repo_tasks_without_llm(monkeypatch):
    # If the deterministic pre-route works, complete_chain is never called.
    def boom(*a, **k):
        raise AssertionError("LLM dispatcher should not run for explicit repo tasks")
    monkeypatch.setattr(team, "complete_chain", boom)
    for task in REPO_TASKS:
        agent_id, reason = team.select_agent(task)
        assert agent_id == "repo-engineer", f"{task!r} -> {agent_id}"


def test_fallback_select_maps_repo_tasks():
    for task in REPO_TASKS:
        assert team._fallback_select(task) == "repo-engineer", task


def test_non_repo_tasks_unaffected():
    for task in NON_REPO_TASKS:
        assert team._fallback_select(task) != "repo-engineer", task
