"""Tier-3 CODING builds must run on an agent that can BUILD AND VERIFY.

Regression (live test 2026-07): the dispatcher picked `architect` (no edit_file /
run_bash) for a complex build — it flailed with 18 raw writes and finished
UNVERIFIED. The orchestrator now repins such picks to `coder`.
"""
from core import orchestrator, agents as team


def _fake_classify(tier=3, task_type="coding"):
    return lambda *a, **k: {"tier": tier, "task_type": task_type, "requires_web": False,
                            "reason": "test", "routed_model": "test/model"}


def _run(monkeypatch, picked_agent):
    """Route a tier-3 coding task with the dispatcher picking `picked_agent`;
    return the agent id the build was actually dispatched to."""
    seen = {}

    def fake_do_subtask(agent_id, *a, **k):
        seen["agent"] = agent_id
        return "done"

    # These test the single-strong-agent repin path (dispatcher pick -> repin to a builder).
    # The phased build (default) picks coder/frontend by task_type instead, so disable it here
    # to exercise the repin logic this test targets.
    monkeypatch.setenv("AGENT_PHASED_BUILD", "0")
    monkeypatch.setattr(orchestrator, "classify", _fake_classify())
    monkeypatch.setattr(team, "select_agent", lambda *a, **k: (picked_agent, "test pick"))
    monkeypatch.setattr(orchestrator, "_do_subtask", fake_do_subtask)
    orchestrator.handle_task("build a full multi-file todo app with tests", review=False)
    return seen["agent"]


def test_architect_repinned_to_coder(monkeypatch):
    # architect can't edit_file/run_bash -> must be repinned to coder.
    assert _run(monkeypatch, "architect") == "coder"


def test_coder_pick_kept(monkeypatch):
    assert _run(monkeypatch, "coder") == "coder"


def test_frontend_pick_kept(monkeypatch):
    # frontend CAN build+verify (has edit_file + run_bash) -> keep the pick.
    assert _run(monkeypatch, "frontend") == "frontend"


def test_unknown_pick_repinned(monkeypatch):
    # a hallucinated agent id -> repin to coder rather than crash or misbuild.
    assert _run(monkeypatch, "no-such-agent") == "coder"
