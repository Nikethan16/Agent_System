"""Tests for the post-edit syntax verifier (phase 2, core/tools.py)."""
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


def test_write_valid_python_no_warning(ws):
    out = tools.write_file("a.py", "def f():\n    return 1\n")
    assert "Wrote" in out
    assert "SYNTAX CHECK" not in out


def test_write_broken_python_warns(ws):
    out = tools.write_file("a.py", "def f(:\n    return\n")
    assert "SYNTAX CHECK FAILED" in out


def test_edit_into_broken_python_warns(ws):
    tools.write_file("a.py", "x = 1\n")
    out = tools.edit_file("a.py", "x = 1", "x = (1")
    assert "Edited" in out
    assert "SYNTAX CHECK FAILED" in out


def test_broken_json_warns(ws):
    out = tools.write_file("d.json", "{ not valid json ")
    assert "SYNTAX CHECK FAILED" in out


def test_valid_json_ok(ws):
    out = tools.write_file("d.json", '{"a": 1}')
    assert "SYNTAX CHECK" not in out


def test_non_code_file_never_warns(ws):
    out = tools.write_file("notes.md", "# heading\n( unbalanced markdown is fine\n")
    assert "SYNTAX CHECK" not in out


def test_toggle_off(ws, monkeypatch):
    monkeypatch.setenv("AGENT_POSTEDIT_VERIFY", "0")
    out = tools.write_file("a.py", "def f(:\n")
    assert "SYNTAX CHECK" not in out
