"""Tests for the grep / glob code-search tools (core/tools.py)."""
import os
import tempfile

import pytest

from core import tools
from core.tools import using_workspace


@pytest.fixture()
def ws():
    with tempfile.TemporaryDirectory() as d:
        with using_workspace(d):
            os.makedirs(os.path.join(d, "src"))
            with open(os.path.join(d, "src", "a.py"), "w") as f:
                f.write("import os\ndef foo():\n    return 42\n")
            with open(os.path.join(d, "src", "b.py"), "w") as f:
                f.write("def bar():\n    return foo()\n")
            with open(os.path.join(d, "readme.md"), "w") as f:
                f.write("# title\nfoo is great\n")
            yield d


def test_grep_finds_matches_with_location(ws):
    out = tools.grep("def foo")
    assert "src/a.py:2:" in out


def test_grep_include_filter(ws):
    out = tools.grep("foo", include="*.py")
    assert "a.py" in out
    assert "readme.md" not in out   # filtered out by include


def test_grep_no_match(ws):
    out = tools.grep("zzz_not_here")
    assert "No matches" in out


def test_grep_invalid_regex(ws):
    out = tools.grep("(unclosed")
    assert out.startswith("ERROR")


def test_glob_recursive(ws):
    out = tools.glob("**/*.py")
    assert "src/a.py" in out
    assert "src/b.py" in out
    assert "readme.md" not in out


def test_glob_no_match(ws):
    out = tools.glob("**/*.rs")
    assert "No files match" in out


def test_grep_sandboxed(ws):
    out = tools.grep("x", path="../../../etc")
    assert out.startswith("ERROR")


def test_grep_skips_symlink_escaping_workspace(ws, tmp_path):
    # A secret file OUTSIDE the workspace, and a symlink to it INSIDE — grep must not
    # read through the symlink (the realpath containment guard).
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET_NEEDLE\n")
    link = os.path.join(ws, "link.txt")
    try:
        os.symlink(str(secret), link)
    except (OSError, NotImplementedError):
        import pytest
        pytest.skip("symlinks not permitted on this platform/run")
    out = tools.grep("TOPSECRET_NEEDLE")
    # The guard skips the symlink, so there's no match. Assert the symlinked FILE was
    # not matched (its path absent) — not that the needle string is absent, since the
    # "No matches for /TOPSECRET_NEEDLE/" message echoes the search pattern.
    assert "link.txt" not in out
    assert "No matches" in out


def test_glob_skips_symlink_escaping_workspace(ws, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n")
    link = os.path.join(ws, "linked.py")
    try:
        os.symlink(str(outside), link)
    except (OSError, NotImplementedError):
        import pytest
        pytest.skip("symlinks not permitted on this platform/run")
    out = tools.glob("**/*.py")
    assert "linked.py" not in out
