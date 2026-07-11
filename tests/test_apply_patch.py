"""apply_patch: multi-file unified-diff application (tolerant hunk matching) + the
opt-in formatter-on-edit hook."""
import os

from core import tools


def _raw(name):
    """Read the actual on-disk content (read_file adds line numbers)."""
    with open(tools._safe(name), encoding="utf-8") as f:
        return f.read()


def test_apply_patch_edits_existing_file(tmp_path):
    with tools.using_workspace(str(tmp_path)):
        tools.write_file("a.py", "def f():\n    return 1\n")
        patch = (
            "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n"
            " def f():\n-    return 1\n+    return 2\n"
        )
        out = tools.apply_patch(patch)
        assert "updated 1 file" in out
        assert "return 2" in _raw("a.py")


def test_apply_patch_creates_new_file(tmp_path):
    with tools.using_workspace(str(tmp_path)):
        patch = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1,2 @@\n+x = 1\n+y = 2\n"
        out = tools.apply_patch(patch)
        assert "created" in out
        assert "x = 1" in _raw("new.py")


def test_apply_patch_multi_file(tmp_path):
    with tools.using_workspace(str(tmp_path)):
        tools.write_file("m1.py", "a = 1\n")
        tools.write_file("m2.py", "b = 2\n")
        patch = (
            "--- a/m1.py\n+++ b/m1.py\n@@ -1 +1 @@\n-a = 1\n+a = 10\n"
            "--- a/m2.py\n+++ b/m2.py\n@@ -1 +1 @@\n-b = 2\n+b = 20\n"
        )
        out = tools.apply_patch(patch)
        assert "updated 2 file" in out
        assert "a = 10" in _raw("m1.py")
        assert "b = 20" in _raw("m2.py")


def test_apply_patch_reports_unmatchable_hunk(tmp_path):
    with tools.using_workspace(str(tmp_path)):
        tools.write_file("a.py", "real = 1\n")
        patch = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-nonexistent = 99\n+changed = 0\n"
        out = tools.apply_patch(patch)
        assert "could NOT be matched" in out


def test_apply_patch_tolerant_whitespace(tmp_path):
    # hunk context has different indentation than the file -> fuzzy matcher still applies it.
    with tools.using_workspace(str(tmp_path)):
        tools.write_file("a.py", "def g():\n        return 1\n")   # 8-space indent
        patch = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n def g():\n-    return 1\n+    return 42\n"
        out = tools.apply_patch(patch)
        assert "return 42" in _raw("a.py")


def test_apply_patch_empty_is_error(tmp_path):
    with tools.using_workspace(str(tmp_path)):
        assert "ERROR" in tools.apply_patch("")


# ---- formatter-on-edit (opt-in) ---------------------------------------------
def test_formatter_off_by_default(tmp_path):
    with tools.using_workspace(str(tmp_path)):
        tools.write_file("f.py", "x=1\n")                       # unformatted
        tools.edit_file("f.py", "x=1", "y=2")
        assert "y=2" in _raw("f.py")                 # left as-is (no format)


def test_formatter_runs_when_enabled(tmp_path, monkeypatch):
    try:
        import black  # noqa: F401
    except ImportError:
        import pytest
        pytest.skip("black not installed")
    monkeypatch.setenv("AGENT_FORMAT_ON_EDIT", "1")
    with tools.using_workspace(str(tmp_path)):
        tools.write_file("f.py", "def f():\n  x=1\n  return x\n")
        tools.edit_file("f.py", "return x", "return  x")        # trigger a re-write
        assert "x = 1" in _raw("f.py")                                   # black normalized spacing
