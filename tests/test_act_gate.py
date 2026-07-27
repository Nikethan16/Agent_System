"""The 'act, don't just plan' done-gate: a build-intent task that ends having changed NO files
gets re-prompted to actually apply the edits. Catches the live failure where agents produced a
detailed plan/analysis for a code change but wrote zero files (both a LEAD run and a single
agent that deferred)."""
import os

from core import orchestrator as o
from core.tools import using_workspace, current_workspace


def test_build_intent_detection():
    assert o._build_intent("coding", "anything at all")
    assert o._build_intent("frontend", "make a landing page")
    # LEAD runs are task_type 'general' — the build-verb signal must still catch them.
    assert o._build_intent("general", "integrate the helpers into offer_eval.py")
    assert o._build_intent("general", "fix the col_adjust direction bug")
    # Non-build asks must NOT be flagged (so a Q&A/summary isn't forced to write files).
    assert not o._build_intent("general", "what does this repository do")
    assert not o._build_intent("research", "understand and summarize the repo")


def test_no_file_change_on_build_task_triggers_retry(tmp_path):
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    with open(os.path.join(ws, "a.py"), "w") as f:
        f.write("x = 1\n")
    with using_workspace(ws):
        before = o._workspace_sig(current_workspace())
        # The agent only DESCRIBED the change; nothing on disk changed.
        assert o._needs_act_retry(before, "Here is what should be done: edit a.py to ...",
                                  "coding", "fix the bug in a.py") is True


def test_new_file_suppresses_retry(tmp_path):
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    with using_workspace(ws):
        before = o._workspace_sig(current_workspace())
        with open(os.path.join(ws, "new.py"), "w") as f:   # a real change
            f.write("y = 2\n")
        assert o._needs_act_retry(before, "Created new.py", "coding", "write new.py") is False


def test_modified_file_suppresses_retry(tmp_path):
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    p = os.path.join(ws, "a.py")
    with open(p, "w") as f:
        f.write("x = 1\n")
    with using_workspace(ws):
        before = o._workspace_sig(current_workspace())
        with open(p, "w") as f:                            # size changes -> detected
            f.write("x = 1\ny = 2\n")
        assert o._needs_act_retry(before, "edited a.py", "coding", "edit a.py") is False


def test_non_build_task_never_retries(tmp_path):
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    with using_workspace(ws):
        before = o._workspace_sig(current_workspace())
        assert o._needs_act_retry(before, "It is a job-search tool.", "general",
                                  "what does this repo do") is False


def test_failed_run_is_not_a_no_act(tmp_path):
    # A provider error / iteration-cap stop is a DIFFERENT failure — don't add an act-retry on top.
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    with using_workspace(ws):
        before = o._workspace_sig(current_workspace())
        assert o._needs_act_retry(before, "(stopped: iteration cap hit: 30)", "coding",
                                  "fix the bug") is False


def test_skips_vcs_and_caches(tmp_path):
    # Noise dirs (.git, __pycache__, node_modules) must not count as "a change".
    ws = str(tmp_path / "ws")
    os.makedirs(os.path.join(ws, "src"))
    with open(os.path.join(ws, "src", "a.py"), "w") as f:
        f.write("x = 1\n")
    with using_workspace(ws):
        before = o._workspace_sig(current_workspace())
        for noise in (".git", "__pycache__", "node_modules"):
            d = os.path.join(ws, noise)
            os.makedirs(d)
            with open(os.path.join(d, "junk"), "w") as f:
                f.write("noise\n")
        # only VCS/cache noise appeared -> still counts as NO real change -> retry
        assert o._needs_act_retry(before, "described only", "coding", "edit a.py") is True
