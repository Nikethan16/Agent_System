"""Tests for the LEAD master-loop guards: plan-repeat (orch #3) and the
near-cap synthesis nudge (orch #2). Uses a scripted fake model so no keys/cost."""
import json

import pytest

from core import orchestrator as orch
from core.llm import Budget


class _Fn:
    def __init__(self, name, args):
        self.name = name
        self.arguments = json.dumps(args)


class _TC:
    def __init__(self, i, name, args):
        self.id = f"call_{i}"
        self.function = _Fn(name, args)


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [{"id": tc.id, "type": "function",
                                "function": {"name": tc.function.name,
                                             "arguments": tc.function.arguments}}
                               for tc in self.tool_calls]
        return d


class _Resp:
    def __init__(self, msg):
        self.choices = [type("C", (), {"message": msg})()]


def test_replan_guard_injects_execute_nudge(monkeypatch):
    """Identical write_todos twice -> the 3rd model call must have received a
    'do not call write_todos again, execute now' nudge in its messages."""
    plan = [{"text": "step one", "status": "pending"}]
    seen_messages = []
    script = [
        _Msg(tool_calls=[_TC(1, "write_todos", {"todos": plan})]),
        _Msg(tool_calls=[_TC(2, "write_todos", {"todos": plan})]),  # identical re-plan
        _Msg(content="all done"),                                    # finish
    ]
    calls = {"n": 0}

    def fake_chain(models, messages, **kw):
        seen_messages.append([m.get("content") for m in messages if isinstance(m, dict)])
        resp = _Resp(script[calls["n"]])
        calls["n"] += 1
        return resp, 0.0

    monkeypatch.setattr(orch, "complete_chain", fake_chain)
    out = orch._master_loop("do the thing", Budget(max_iterations=50), None, None,
                            review=False, initial_todos=plan)
    assert out == "all done"
    # The 3rd call's messages must contain the execute-now nudge.
    third = " ".join(c or "" for c in seen_messages[2])
    assert "Do NOT call write_todos again" in third


def test_clean_final_returned_normally(monkeypatch):
    plan = [{"text": "x", "status": "pending"}]
    script = [_Msg(content="here is the answer")]
    calls = {"n": 0}

    def fake_chain(models, messages, **kw):
        resp = _Resp(script[calls["n"]])
        calls["n"] += 1
        return resp, 0.0

    monkeypatch.setattr(orch, "complete_chain", fake_chain)
    out = orch._master_loop("q", Budget(max_iterations=50), None, None,
                            review=False, initial_todos=plan)
    assert out == "here is the answer"
