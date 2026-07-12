"""The pipeline's research stage splits into INDEPENDENT sub-questions and runs them
CONCURRENTLY (_split_research + _run_agents_parallel). Uses a scripted fake model +
a threading.Barrier so no keys/cost, and proves the fan-out is genuinely parallel
(not just interleaved) — the barrier only releases if all branches run at once."""
import json
import threading

from core import orchestrator as orch
from core.llm import Budget


class _Resp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]


# ---- _split_research --------------------------------------------------------
def test_split_research_parses_questions(monkeypatch):
    def fake_chain(models, messages, **kw):
        return _Resp('{"questions": ["What is A?", "What is B?", "What is C?"]}'), 0.0

    monkeypatch.setattr(orch, "complete_chain", fake_chain)
    qs = orch._split_research("research A, B, and C then build it", Budget())
    assert qs == ["What is A?", "What is B?", "What is C?"]


def test_split_research_caps_and_handles_junk(monkeypatch):
    monkeypatch.setattr(orch, "complete_chain",
                        lambda *a, **k: (_Resp("not json at all"), 0.0))
    assert orch._split_research("x", Budget()) == []      # unparseable -> no split

    monkeypatch.setattr(orch, "complete_chain",
                        lambda *a, **k: (_Resp('{"questions": ["a","b","c","d","e","f"]}'), 0.0))
    qs = orch._split_research("x", Budget(), max_q=4)
    assert qs == ["a", "b", "c", "d"]                     # capped at max_q


# ---- _run_agents_parallel ---------------------------------------------------
def test_run_agents_parallel_is_concurrent_and_ordered(monkeypatch):
    """All branches run at the SAME time (barrier releases), results keep spec order,
    and a failing branch is isolated (siblings survive)."""
    specs = [{"agent": "research", "instruction": "Q1"},
             {"agent": "research", "instruction": "Q2"},
             {"agent": "research", "instruction": "Q3"}]
    barrier = threading.Barrier(len(specs), timeout=5)

    def fake_run(agent_id, instruction, **kw):
        barrier.wait()                 # blocks until ALL branches arrive -> proves concurrency
        if instruction == "Q2":
            raise RuntimeError("boom")
        return f"answer to {instruction}"

    monkeypatch.setattr(orch.team, "run", fake_run)
    pairs = orch._run_agents_parallel(specs, Budget(), None, None)
    assert [a for a, _ in pairs] == ["research", "research", "research"]
    assert pairs[0][1] == "answer to Q1"
    assert pairs[2][1] == "answer to Q3"
    assert "parallel task failed" in pairs[1][1] and "boom" in pairs[1][1]  # isolated failure


def test_run_agents_parallel_unknown_agent_falls_back(monkeypatch):
    seen = {}

    def fake_run(agent_id, instruction, **kw):
        seen["agent"] = agent_id
        return "ok"

    monkeypatch.setattr(orch.team, "run", fake_run)
    monkeypatch.setattr(orch.team, "_fallback_select", lambda t: "coder")
    pairs = orch._run_agents_parallel([{"agent": "no_such_agent", "instruction": "build x"}],
                                      Budget(), None, None)
    assert seen["agent"] == "coder"          # unknown id routed through the keyword fallback
    assert pairs == [("coder", "ok")]


# ---- pipeline STAGE 1 fan-out -----------------------------------------------
def test_pipeline_research_fans_out(monkeypatch):
    """When the goal splits into >1 questions, each runs as its own research agent and
    the findings all land on the blackboard before the plan/build stages."""
    monkeypatch.setattr(orch, "_split_research", lambda *a, **k: ["Q about X", "Q about Y"])
    monkeypatch.setenv("AGENT_MAX_PARALLEL", "4")
    monkeypatch.setattr(orch, "MAX_PARALLEL_FANOUT", 4)
    # keep the map cheap + deterministic
    import core.repomap as rm
    monkeypatch.setattr(rm, "build_map", lambda *a, **k: "")

    research_calls = []

    def fake_run(agent_id, instruction, **kw):
        if agent_id == "research":
            research_calls.append(instruction)
            return f"findings for: {instruction[:40]}"
        return f"{agent_id} did the work"        # architect / coder / reviewer

    monkeypatch.setattr(orch.team, "run", fake_run)

    plan_events = []
    out = orch._pipeline("research X and Y then build a tool", Budget(), plan_events.append,
                         None, review=False, task_type="coding")
    assert len(research_calls) == 2                        # both sub-questions investigated
    assert any("Q about X" in c for c in research_calls)
    assert any("Q about Y" in c for c in research_calls)
    assert "coder did the work" in out                    # build stage still produced the result
