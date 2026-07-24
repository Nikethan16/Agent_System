"""Tier floor (regression for the deep-test finding that EVERY task — even a hard multi-tenant
build — collapsed to the cheap flash model because _effective_tier only ever downgraded).

floor_tier must RAISE the effective tier for hard builds while still preserving the existing
cost-downgrade (an easy task on an expensive agent stays cheap)."""
from core.agents import _effective_tier


def test_downgrade_preserved():
    # easy task routed onto a tier-2 specialist -> use the cheaper tier (unchanged behavior)
    assert _effective_tier("tier2", "tier1") == "tier1"
    assert _effective_tier("tier2", None) == "tier2"


def test_floor_raises_for_hard_build():
    # the hard-build path passes floor_tier='tier3' -> a tier-2 coder is lifted to tier3
    assert _effective_tier("tier2", "tier3", floor_tier="tier3") == "tier3"
    assert _effective_tier("tier2", None, floor_tier="tier3") == "tier3"


def test_floor_overrides_downgrade():
    # even if the router downgraded to tier1, an explicit floor wins (hard build must not
    # implement on the cheap model)
    assert _effective_tier("tier2", "tier1", floor_tier="tier3") == "tier3"


def test_floor_never_lowers():
    # floor is a LOWER bound only — it never drops a naturally-higher tier
    assert _effective_tier("tier3", None, floor_tier="tier2") == "tier3"
