"""The LEAD loop must STOP early when it makes no progress, instead of grinding to the round cap
burning tokens every round. _stall_next tracks the shared work record (blackboard digest): it
counts unchanged rounds and signals a stop after MAX_STALL_ROUNDS."""
from core import orchestrator as o


def test_progress_resets_the_stall_counter():
    s, stop = o._stall_next(0, "digest-v1", None)      # first look (changed from None)
    assert s == 0 and not stop
    s, stop = o._stall_next(2, "digest-v2", "digest-v1")   # grew -> reset
    assert s == 0 and not stop


def test_unchanged_rounds_accumulate_then_stop():
    s, stop = o._stall_next(0, "same", "same"); assert s == 1 and not stop
    s, stop = o._stall_next(1, "same", "same"); assert s == 2 and not stop
    s, stop = o._stall_next(2, "same", "same"); assert s == 3 and stop     # hit the cap -> stop


def test_max_stall_override():
    # With a cap of 2, two unchanged rounds is enough.
    s, stop = o._stall_next(1, "x", "x", max_stall=2)
    assert s == 2 and stop


def test_default_cap_is_configured():
    assert o.MAX_STALL_ROUNDS >= 2      # sane default (env-tunable)
