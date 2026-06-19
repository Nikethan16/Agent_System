"""Tests for dispatcher hardening + tier/model alignment (orch #4)."""
from core import agents


def test_effective_tier_uses_cheaper():
    # tier-1 task routed to a tier-2 agent -> run at tier1.
    assert agents._effective_tier("tier2", 1) == "tier1"
    # tier-3 task with a tier-2 agent -> still the agent's tier2 (don't upgrade).
    assert agents._effective_tier("tier2", 3) == "tier2"
    # no routed tier -> agent tier unchanged.
    assert agents._effective_tier("tier2", None) == "tier2"
    # equal -> same.
    assert agents._effective_tier("tier2", 2) == "tier2"


def test_tier_num_parsing():
    assert agents._tier_num("tier3") == 3
    assert agents._tier_num("tier1") == 1
    assert agents._tier_num("garbage") == 2   # safe default


def test_select_agent_tolerates_bare_id(monkeypatch):
    """Dispatcher returns a non-JSON reply naming an agent -> we still pick it,
    rather than silently dropping to keyword matching (the live-trace bug)."""
    class _Msg:
        content = "I think the coder agent is best here."

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})()]

    monkeypatch.setattr(agents, "complete_chain", lambda *a, **k: (_Resp(), 0.0))
    aid, reason = agents.select_agent("do a thing")
    assert aid == "coder"


def test_select_agent_keyword_fallback_on_empty(monkeypatch):
    class _Msg:
        content = ""

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})()]

    monkeypatch.setattr(agents, "complete_chain", lambda *a, **k: (_Resp(), 0.0))
    aid, reason = agents.select_agent("explain how recursion works")
    # explanation phrasing -> general (tool-less), per _fallback_select
    assert aid == "general"
