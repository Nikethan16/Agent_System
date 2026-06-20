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


def test_tool_using_agents_not_downgraded():
    """Regression: a tool-using agent (research/coder) must NOT be downgraded to a
    tier-1 model just because the task routed tier-1 — that broke tool-calling.
    Only tool-less agents (general) may run on the cheaper routed tier."""
    research = agents.agents.get("research")
    general = agents.agents.get("general")
    assert research.tools          # has tools
    assert not general.tools       # tool-less
    # the orchestrator passes downgrade_tier=None for tool-using agents:
    dt_research = 1 if not research.tools else None
    dt_general = 1 if not general.tools else None
    assert dt_research is None      # research keeps its own (tier2) model
    assert dt_general == 1          # general may drop to tier1
    assert agents._effective_tier(research.tier, dt_research) == research.tier
