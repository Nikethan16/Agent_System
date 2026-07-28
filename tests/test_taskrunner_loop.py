"""The per-feature verify-and-retry loop in server/taskrunner.run_program ('loop engineering').

A feature is 'done' only when it passes the gate (evaluate_feature). If it fails it is re-driven
with feedback up to 2 more times; still failing -> flagged 'needs_attention' and the run CONTINUES
to the next feature (flag-and-continue). We stub the orchestrator functions run_program imports at
call-time, so we exercise the loop control flow deterministically without any model calls.
"""
import types

import core.orchestrator as orch
from server import taskrunner


class FakeBudget:
    def __init__(self, max_usd=10.0):
        self.max_usd = max_usd
        self.spent_usd = 0.0


def _install(monkeypatch, handle_task, evaluate_feature):
    """Patch the three names run_program imports from core.orchestrator (and current_workspace)."""
    monkeypatch.setattr(orch, "handle_task", handle_task, raising=False)
    monkeypatch.setattr(orch, "evaluate_feature", evaluate_feature, raising=False)
    monkeypatch.setattr(orch, "_workspace_sig", lambda ws: {}, raising=False)
    # current_workspace is imported from core.tools inside run_program; a stub avoids fs walks.
    import core.tools as tools
    monkeypatch.setattr(tools, "current_workspace", lambda: "", raising=False)


def _collect_emit():
    events = []
    return events, (lambda ev: events.append(ev))


def _active(prompt: str) -> str:
    """The feature currently being worked = the text right after the 'yet:\\n' marker.
    (The 'Already completed' list also names prior features, so a bare substring test would
    match the wrong one — always key off the active-task marker.)"""
    if "yet:\n" not in prompt:
        return ""
    return prompt.split("yet:\n", 1)[1].split("\n", 1)[0].strip()


def test_passing_feature_is_verified_first_try(monkeypatch):
    calls = {"n": 0}

    def ht(prompt, **kw):
        calls["n"] += 1
        return "did it"

    def ev(task, result, before_sig, budget, **kw):
        return True, ""

    _install(monkeypatch, ht, ev)
    events, emit = _collect_emit()
    out = taskrunner.run_program(["feature A", "feature B"], "", FakeBudget(), emit)

    assert calls["n"] == 2                       # one build per feature, no re-tries
    last = [e for e in events if e["type"] == "program"][-1]
    assert last["done"] == 2 and last["total"] == 2
    assert all(t["status"] == "verified" for t in last["tasks"])
    assert all(t["attempts"] == 1 for t in last["tasks"])
    assert "Verified 2/2" in out


def test_inner_handle_task_review_is_disabled(monkeypatch):
    """evaluate_feature is the single QA gate -> the inner handle_task must not double-review."""
    seen = {}

    def ht(prompt, **kw):
        seen.update(kw)
        return "x"

    _install(monkeypatch, ht, lambda *a, **k: (True, ""))
    _, emit = _collect_emit()
    taskrunner.run_program(["a", "b"], "", FakeBudget(), emit)
    assert seen.get("review") is False


def test_red_feature_retries_then_flagged(monkeypatch):
    prompts = []

    def ht(prompt, **kw):
        prompts.append(prompt)
        return "attempted"

    def ev(task, result, before_sig, budget, **kw):
        return False, "2 tests still failing: test_x, test_y"

    _install(monkeypatch, ht, ev)
    events, emit = _collect_emit()
    out = taskrunner.run_program(["hard feature", "easy feature"], "", FakeBudget(), emit)

    last = [e for e in events if e["type"] == "program"][-1]
    hard = last["tasks"][0]
    assert hard["status"] == "needs_attention"    # never a false 'done'
    assert hard["attempts"] == 3                   # 1 build + 2 re-tries (the cap)
    # The concrete failure feedback is fed back into attempts 2 and 3.
    hard_prompts = [p for p in prompts if _active(p) == "hard feature"]
    assert len(hard_prompts) == 3
    assert sum("PREVIOUS ATTEMPT FAILED" in p for p in hard_prompts) == 2
    assert "2 tests still failing" in hard_prompts[-1]
    assert "need" in out.lower() and "attention" in out.lower()


def test_flag_and_continue_reaches_last_feature(monkeypatch):
    ran = []

    def ht(prompt, **kw):
        ran.append(_active(prompt))
        return "res"

    def ev(task, result, before_sig, budget, **kw):
        # F2 can never pass; F1 and F3 pass immediately.
        return (task != "F2"), ("F2 is broken" if task == "F2" else "")

    _install(monkeypatch, ht, ev)
    events, emit = _collect_emit()
    taskrunner.run_program(["F1", "F2", "F3"], "", FakeBudget(), emit)

    last = [e for e in events if e["type"] == "program"][-1]
    statuses = [t["status"] for t in last["tasks"]]
    assert statuses == ["verified", "needs_attention", "verified"]
    assert last["done"] == 2                       # only the two verified count
    assert "F3" in ran                             # the stuck F2 did NOT block F3


def test_fix_on_second_attempt_is_verified(monkeypatch):
    state = {"n": 0}

    def ht(prompt, **kw):
        state["n"] += 1
        return "r"

    def ev(task, result, before_sig, budget, **kw):
        # Fails the first check, passes the second (a successful re-work).
        return (state["n"] >= 2), ("fix the import" if state["n"] < 2 else "")

    _install(monkeypatch, ht, ev)
    events, emit = _collect_emit()
    taskrunner.run_program(["one feature"], "", FakeBudget(), emit)

    last = [e for e in events if e["type"] == "program"][-1]
    assert last["tasks"][0]["status"] == "verified"
    assert last["tasks"][0]["attempts"] == 2
    assert last["done"] == 1


def test_budget_exhaustion_skips_the_rest(monkeypatch):
    budget = FakeBudget(max_usd=1.0)

    def ht(prompt, **kw):
        budget.spent_usd = 1.0                     # first feature spends the whole cap
        return "r"

    _install(monkeypatch, ht, lambda *a, **k: (True, ""))
    events, emit = _collect_emit()
    taskrunner.run_program(["A", "B", "C"], "", budget, emit)

    last = [e for e in events if e["type"] == "program"][-1]
    statuses = [t["status"] for t in last["tasks"]]
    assert statuses[0] == "verified"
    assert statuses[1] == "skipped" and statuses[2] == "skipped"


def test_exception_marks_error_and_continues(monkeypatch):
    def ht(prompt, **kw):
        if _active(prompt) == "boom feature":
            raise RuntimeError("kaboom")
        return "r"

    _install(monkeypatch, ht, lambda *a, **k: (True, ""))
    events, emit = _collect_emit()
    taskrunner.run_program(["boom feature", "good feature"], "", FakeBudget(), emit)

    last = [e for e in events if e["type"] == "program"][-1]
    assert last["tasks"][0]["status"] == "error"
    assert last["tasks"][1]["status"] == "verified"   # run continued past the error


def test_public_carries_attempts_and_status():
    prog = [{"text": "x", "status": "needs_attention", "result": "", "attempts": 3}]
    pub = taskrunner._public(prog)
    assert pub == [{"text": "x", "status": "needs_attention", "attempts": 3}]
