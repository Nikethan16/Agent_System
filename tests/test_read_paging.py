"""Tests for read_file paging / caps / line numbers (core/tools.py)."""
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
    with open(os.path.join(ws, name), "w", encoding="utf-8") as f:
        f.write(content)


def test_line_numbers_and_footer(ws):
    _write(ws, "a.py", "alpha\nbeta\ngamma\n")
    out = tools.read_file("a.py")
    assert "1: alpha" in out
    assert "2: beta" in out
    assert "3: gamma" in out
    assert "End of file — 3 lines" in out


def test_offset_and_limit(ws):
    _write(ws, "a.py", "\n".join(f"line{i}" for i in range(1, 11)) + "\n")
    out = tools.read_file("a.py", offset=4, limit=3)
    assert "4: line4" in out
    assert "6: line6" in out
    assert "line7" not in out
    assert "Showing lines 4-6 of 10" in out
    assert "offset=7 to continue" in out


def test_line_count_cap_pages(ws):
    _write(ws, "big.py", "\n".join(f"L{i}" for i in range(1, 5001)) + "\n")
    out = tools.read_file("big.py")
    assert "1: L1" in out
    # default cap is 2000 lines -> must NOT show line 2001 and must offer paging
    assert "2001: L2001" not in out
    assert "offset=2001 to continue" in out


def test_long_line_truncated(ws):
    _write(ws, "a.py", "x" * 5000 + "\n")
    out = tools.read_file("a.py")
    assert "[line truncated]" in out


def test_empty_file(ws):
    _write(ws, "e.py", "")
    out = tools.read_file("e.py")
    assert "Empty file" in out


def test_missing_file_errors(ws):
    out = tools.read_file("nope.py")
    assert out.startswith("ERROR")
