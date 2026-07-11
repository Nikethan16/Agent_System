"""Phase-3 polish: degenerate-output detector, read-before-edit staleness guard,
persistence overlay wiring."""
import os
import time
import tempfile

from core import tools
from core import agent as A
from core import agents as team


# ---- 3.3 degenerate-output detection ---------------------------------------
def test_degenerate_detection():
    assert A._looks_degenerate("!" * 200)                       # char spam
    assert A._looks_degenerate("spam " * 60)                    # word repeat
    assert not A._looks_degenerate("A normal answer: def f(): return 1  # done")
    assert not A._looks_degenerate("=" * 50)                    # short md rule — not flagged
    assert not A._looks_degenerate("")                          # empty


# ---- 3.2 read-before-edit staleness guard ----------------------------------
def test_staleness_guard_blocks_stale_edit():
    with tools.using_workspace(tempfile.mkdtemp()):
        tools.write_file("a.py", "a = 1\n")                     # records mtime
        full = tools._safe("a.py")
        # Simulate an out-of-band change (newer mtime) after our recorded touch.
        future = time.time() + 100
        os.utime(full, (future, future))
        r = tools.edit_file("a.py", "a = 1", "a = 2")
        assert r.startswith("ERROR") and "changed since" in r
        # Re-reading clears the staleness, then the edit applies.
        tools.read_file("a.py")
        r2 = tools.edit_file("a.py", "a = 1", "a = 2")
        assert "Edited" in r2


def test_normal_edit_not_flagged():
    with tools.using_workspace(tempfile.mkdtemp()):
        tools.write_file("b.py", "x = 1\n")
        r = tools.edit_file("b.py", "x = 1", "x = 2")           # our own write, no drift
        assert "Edited" in r


# ---- 3.1 persistence overlay wiring ----------------------------------------
def test_persistence_overlay_applies_to_execution_agents():
    assert "PERSISTENCE" in team._EXEC_OVERLAY
    coder = team.agents.get("coder")
    assert "run_bash" in coder.tools          # so the overlay is appended for it
    doc = team.agents.get("doc")
    assert "run_bash" not in doc.tools        # tool-less writer doesn't get it
    # Composition: coder (edit+exec tools) gets BOTH overlays; general gets none.
    both = team._overlays_for(coder)
    assert "FILE RULES" in both and "PERSISTENCE" in both
    assert team._overlays_for(team.agents.get("general")) == ""
