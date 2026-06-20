"""Tests for the fuzzy edit_file cascade (core/tools.py).

Proves BOTH directions:
  * near-miss snippets (whitespace / indentation drift) still land, AND
  * low-confidence / ambiguous / not-found cases REFUSE rather than guess.
"""
import os
import tempfile

import pytest

from core import tools
from core.tools import using_workspace


@pytest.fixture()
def ws():
    with tempfile.TemporaryDirectory() as d:
        with using_workspace(d):
            yield d


def _write(ws, name, content):
    with open(os.path.join(ws, name), "w", encoding="utf-8", newline="") as f:
        f.write(content)


def _read(ws, name):
    # newline="" so on-disk line endings are NOT translated (lets us assert CRLF).
    with open(os.path.join(ws, name), encoding="utf-8", newline="") as f:
        return f.read()


# ---- positive: near-misses must land ---------------------------------------

def test_exact_match(ws):
    _write(ws, "a.py", "x = 1\ny = 2\n")
    out = tools.edit_file("a.py", "y = 2", "y = 3")
    assert "Edited" in out
    assert "y = 3" in _read(ws, "a.py")


def test_indentation_drift_lands(ws):
    # File has 8-space indent; model supplies 4-space indent.
    _write(ws, "a.py", "def f():\n        return 1\n")
    out = tools.edit_file("a.py", "    return 1", "    return 2")
    assert "Edited" in out
    assert "return 2" in _read(ws, "a.py")


def test_whitespace_run_drift_lands(ws):
    # File uses a tab; model supplies spaces.
    _write(ws, "a.py", "if  x:\n\tpass\n")
    out = tools.edit_file("a.py", "if x:", "if y:")
    assert "Edited" in out
    assert "if y:" in _read(ws, "a.py")


def test_block_anchor_lands_on_close_middle(ws):
    original = "def g():\n    a = compute(1)\n    return a\n"
    _write(ws, "a.py", original)
    # First+last lines match; middle slightly off (compute(1) vs compute( 1 )).
    snippet = "def g():\n    a = compute( 1 )\n    return a"
    out = tools.edit_file("a.py", snippet, "def g():\n    return 0")
    assert "Edited" in out
    assert "return 0" in _read(ws, "a.py")


# ---- negative: must REFUSE, not guess --------------------------------------

def test_not_found_refuses(ws):
    _write(ws, "a.py", "x = 1\n")
    out = tools.edit_file("a.py", "totally_absent_symbol = 99", "z = 0")
    assert out.startswith("ERROR")
    assert "not found" in out
    assert _read(ws, "a.py") == "x = 1\n"   # unchanged


def test_ambiguous_refuses(ws):
    _write(ws, "a.py", "v = 1\nv = 1\n")
    out = tools.edit_file("a.py", "v = 1", "v = 2")
    assert out.startswith("ERROR")
    assert "unique" in out or "matches" in out
    assert _read(ws, "a.py") == "v = 1\nv = 1\n"   # unchanged


def test_ambiguous_resolved_by_replace_all(ws):
    _write(ws, "a.py", "v = 1\nv = 1\n")
    out = tools.edit_file("a.py", "v = 1", "v = 2", replace_all=True)
    assert "Edited" in out
    assert _read(ws, "a.py") == "v = 2\nv = 2\n"


def test_block_anchor_below_threshold_refuses(ws):
    # First+last lines match, but the middle is wildly different -> no guess.
    _write(ws, "a.py", "def g():\n    a = compute(1)\n    return a\n")
    snippet = "def g():\n    completely_unrelated_line_here = xyz\n    return a"
    out = tools.edit_file("a.py", snippet, "def g():\n    return 0")
    assert out.startswith("ERROR")
    assert "return 0" not in _read(ws, "a.py")   # unchanged


def test_empty_old_string_refuses(ws):
    _write(ws, "a.py", "x = 1\n")
    out = tools.edit_file("a.py", "", "z = 0")
    assert out.startswith("ERROR")


def test_missing_file_refuses(ws):
    out = tools.edit_file("nope.py", "x", "y")
    assert out.startswith("ERROR")
    assert "not found" in out


def test_crlf_preserved(ws):
    _write(ws, "a.py", "x = 1\r\ny = 2\r\n")
    out = tools.edit_file("a.py", "y = 2", "y = 3")
    assert "Edited" in out
    assert _read(ws, "a.py") == "x = 1\r\ny = 3\r\n"
