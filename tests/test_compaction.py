"""Tests for within-run context compaction (phase 2, core/agent.py)."""
import pytest

from core import agent as ag
from core.llm import Budget


def _big_history(n=40):
    msgs = [{"role": "system", "content": "SYS"}]
    for i in range(n):
        msgs.append({"role": "user", "content": "U" * 2000 + f" turn{i}"})
        msgs.append({"role": "assistant", "content": "A" * 2000 + f" reply{i}"})
    return msgs


def test_small_history_untouched(monkeypatch):
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"}]
    out = ag._compact_messages(list(msgs), budget=Budget())
    assert out == msgs


def test_large_history_compacted(monkeypatch):
    monkeypatch.setattr(ag.registry, "context_budget", lambda: 4000)

    class _Msg:
        content = "SUMMARY: did stuff; file x.py created; remains: tests."

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})()]

    # compaction uses the fallback chain (complete_chain) now
    monkeypatch.setattr(ag, "complete_chain", lambda *a, **k: (_Resp(), 0.0))
    msgs = _big_history(40)
    out = ag._compact_messages(msgs, budget=Budget(max_iterations=999))
    assert len(out) < len(msgs)
    assert out[0]["content"] == "SYS"                       # system preserved
    assert "Summary of earlier work" in out[1]["content"]   # summary injected
    assert out[-1] == msgs[-1]                              # recent tail preserved


def test_tail_never_starts_on_tool_message(monkeypatch):
    monkeypatch.setattr(ag.registry, "context_budget", lambda: 2000)

    class _Msg:
        content = "summary"

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})()]

    monkeypatch.setattr(ag, "complete_chain", lambda *a, **k: (_Resp(), 0.0))
    # Build history whose natural keep-window would START on a 'tool' message.
    msgs = [{"role": "system", "content": "s"}]
    for i in range(20):
        msgs.append({"role": "assistant", "content": "x" * 1500,
                     "tool_calls": [{"id": f"c{i}", "function": {"name": "read_file"}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "y" * 1500})
    out = ag._compact_messages(msgs, budget=Budget(max_iterations=999))
    # After the injected summary, the first kept message must not be a 'tool' msg.
    assert out[2]["role"] != "tool"


def test_compaction_failure_is_safe(monkeypatch):
    monkeypatch.setattr(ag.registry, "context_budget", lambda: 2000)

    def _boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr(ag, "complete_chain", _boom)
    msgs = _big_history(40)
    out = ag._compact_messages(msgs, budget=Budget())
    assert out == msgs   # unchanged on failure — never breaks the run
