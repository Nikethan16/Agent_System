"""Compaction must ALWAYS bound the context — even when the summariser model call fails (which
happens under exactly the provider pressure a long run creates). Previously it returned the full
history on failure, letting the window grow unbounded and burn tokens every round."""
import core.agent as agent


def _big_history(n_pairs: int = 30, size: int = 4000):
    msgs = [{"role": "system", "content": "system prompt"}]
    for i in range(n_pairs):
        msgs.append({"role": "user", "content": "u" * size})
        msgs.append({"role": "assistant", "content": "a" * size})
    return msgs


def test_deterministic_trim_when_summariser_raises(monkeypatch):
    monkeypatch.delenv("AGENT_COMPACT", raising=False)
    monkeypatch.setattr(agent, "complete_chain", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider down")))
    msgs = _big_history()
    out = agent._compact_messages(msgs)
    assert len(out) < len(msgs)                       # history was bounded, not left full
    assert out[0]["role"] == "system"                 # head (system) preserved
    assert "trimmed" in out[1]["content"].lower()     # deterministic trim marker inserted
    assert out[-1] == msgs[-1]                         # most-recent turn preserved


def test_deterministic_trim_when_summary_empty(monkeypatch):
    monkeypatch.delenv("AGENT_COMPACT", raising=False)

    class _Msg:
        content = "   "     # whitespace-only summary -> treated as failure -> trim

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})()]

    monkeypatch.setattr(agent, "complete_chain", lambda *a, **k: (_Resp(), None))
    msgs = _big_history()
    out = agent._compact_messages(msgs)
    assert len(out) < len(msgs)
    assert "trimmed" in out[1]["content"].lower()


def test_summary_used_when_available(monkeypatch):
    monkeypatch.delenv("AGENT_COMPACT", raising=False)

    class _Msg:
        content = "SUMMARY: the agent did X, Y, Z."

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})()]

    monkeypatch.setattr(agent, "complete_chain", lambda *a, **k: (_Resp(), None))
    out = agent._compact_messages(_big_history())
    assert "Summary of earlier work" in out[1]["content"]
    assert "did X, Y, Z" in out[1]["content"]


def test_small_history_is_untouched():
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"}]
    assert agent._compact_messages(msgs) == msgs      # below threshold -> no change
