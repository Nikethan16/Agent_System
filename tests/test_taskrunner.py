"""Sequential task-runner: an explicit ordered list runs one-by-one with progress events.
handle_task is stubbed so these stay fully offline/deterministic."""
import core.orchestrator as orch
from core.llm import Budget
from server import taskrunner


# ---- parsing (only explicit lists trigger sequential mode) -----------------
def test_parse_numbered_list():
    tasks = taskrunner.parse_tasks("Please do:\n1. build login\n2) build dashboard\n3. write tests")
    assert tasks == ["build login", "build dashboard", "write tests"]


def test_parse_bulleted_list():
    assert taskrunner.parse_tasks("- add a header\n- add a footer") == ["add a header", "add a footer"]


def test_prose_and_single_item_do_not_trigger():
    assert taskrunner.parse_tasks("build me a login page and then a dashboard") == []
    assert taskrunner.parse_tasks("1. just one thing") == []
    assert taskrunner.parse_tasks("") == []


# ---- execution -------------------------------------------------------------
# evaluate_feature (the per-feature done-gate) is stubbed to pass so these stay offline and
# focus on the sequencing/progress contract; the gate's own logic is covered in
# tests/test_taskrunner_loop.py.
def test_runs_each_task_in_order_with_progress(monkeypatch):
    calls, events = [], []
    monkeypatch.setattr(orch, "handle_task", lambda prompt, **kw: calls.append(prompt) or "did it")
    monkeypatch.setattr(orch, "evaluate_feature", lambda *a, **k: (True, ""))
    out = taskrunner.run_program(["build A", "build B"], context="", budget=Budget(),
                                 emit=lambda e: events.append(e))
    assert len(calls) == 2
    assert "build A" in calls[0] and "TASK 1 OF 2" in calls[0]
    assert "build B" in calls[1] and "build A (done)" in calls[1]   # prior progress carried forward
    progs = [e for e in events if e["type"] == "program"]
    assert progs[-1]["done"] == 2 and progs[-1]["total"] == 2
    assert all(t["status"] == "verified" for t in progs[-1]["tasks"])
    assert "Verified 2/2 features" in out


def test_stops_and_skips_when_budget_exhausted(monkeypatch):
    monkeypatch.setattr(orch, "handle_task", lambda prompt, **kw: "x")
    b = Budget(max_usd=0.01)
    b.spent_usd = 0.05                                   # already over the cap
    events = []
    taskrunner.run_program(["A", "B"], context="", budget=b, emit=lambda e: events.append(e))
    prog = [e for e in events if e["type"] == "program"][-1]
    assert prog["done"] == 0
    assert all(t["status"] == "skipped" for t in prog["tasks"])


def test_task_error_is_isolated(monkeypatch):
    def flaky(prompt, **kw):
        if "B" in prompt.split("TASK", 1)[-1][:40]:
            raise RuntimeError("boom")
        return "ok"
    monkeypatch.setattr(orch, "handle_task", flaky)
    monkeypatch.setattr(orch, "evaluate_feature", lambda *a, **k: (True, ""))
    events = []
    out = taskrunner.run_program(["A", "B", "C"], context="", budget=Budget(),
                                 emit=lambda e: events.append(e))
    prog = [e for e in events if e["type"] == "program"][-1]
    statuses = [t["status"] for t in prog["tasks"]]
    assert statuses[0] == "verified" and statuses[1] == "error" and statuses[2] == "verified"  # C still runs
    assert "Verified 2/3 features" in out
