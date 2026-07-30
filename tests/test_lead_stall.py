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


# ---- the SIGNAL must be monotonic: a productive run must never falsely stall ----
# Regression for the original bug where board.digest() (truncated at 6000 chars) froze on big
# runs, so a still-progressing lead looked stalled. The real loop feeds _stall_next a monotonic
# progress_ticks counter (+1 on every did_work round); simulate both patterns here.

def test_productive_run_never_stalls(monkeypatch):
    monkeypatch.setattr(o, "MAX_STALL_ROUNDS", 3)
    stall, last, ticks, stopped = 0, 0, 0, False
    for _ in range(30):                 # far more than any round cap
        ticks += 1                       # did_work EVERY round -> counter advances
        stall, stop = o._stall_next(stall, ticks, last)
        last = ticks
        stopped = stopped or stop
    assert not stopped                   # monotonic progress -> never a false stop


def test_idle_run_stalls_after_cap(monkeypatch):
    monkeypatch.setattr(o, "MAX_STALL_ROUNDS", 3)
    stall, last, ticks = 0, 0, 0
    stops = []
    for _ in range(5):                   # did_work False -> ticks frozen (planning/chatting only)
        stall, stop = o._stall_next(stall, ticks, last, max_stall=o.MAX_STALL_ROUNDS)
        last = ticks
        stops.append(stop)
    assert any(stops)                    # a genuinely idle loop does stop


def test_work_after_idle_resets(monkeypatch):
    # idle, idle, THEN work -> the counter resets and it keeps going.
    stall, last, ticks = 0, 0, 0
    stall, s1 = o._stall_next(stall, ticks, last); last = ticks         # idle (stall 1)
    stall, s2 = o._stall_next(stall, ticks, last); last = ticks         # idle (stall 2)
    ticks += 1                                                          # did_work
    stall, s3 = o._stall_next(stall, ticks, last, max_stall=3); last = ticks
    assert stall == 0 and not s3
