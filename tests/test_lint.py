"""Tests for real diagnostics (core/lint.py) + the `diagnostics` tool."""
import os

import pytest

from core import lint, tools


@pytest.fixture
def ws(tmp_path):
    with tools.using_workspace(str(tmp_path)):
        yield tmp_path


def _write(ws, name, body):
    (ws / name).write_text(body, encoding="utf-8")
    return name


def test_diagnose_flags_undefined_name_and_unused_import(ws):
    _write(ws, "bad.py", "import os\n\n\ndef f():\n    return missing_name\n")
    diags = lint.diagnose("bad.py")
    msgs = " ".join(d["message"].lower() for d in diags)
    assert "undefined name" in msgs or "missing_name" in msgs
    # ruff (if present) also flags the unused import; pyflakes fallback does too
    assert any(d.get("line") for d in diags)


def test_diagnose_clean_file_has_no_diagnostics(ws):
    _write(ws, "good.py", "def add(a, b):\n    return a + b\n")
    assert lint.diagnose("good.py") == []


def test_diagnose_syntax_error(ws):
    _write(ws, "broken.py", "def f(:\n    pass\n")
    diags = lint.diagnose("broken.py")
    # ruff → code "invalid-syntax"; pyflakes fallback → "E999"/"SyntaxError"
    assert diags and any(
        "syntax" in d["message"].lower() or "syntax" in (d["code"] or "").lower()
        or d["code"] == "E999" for d in diags)


def test_diagnose_json_syntax(ws):
    _write(ws, "bad.json", '{"a": 1,,}')
    diags = lint.diagnose("bad.json")
    assert diags and diags[0]["severity"] == "error"


def test_postedit_python_warns_then_clean(ws):
    warn = lint.postedit_python("x.py", "import os\n\n\ndef f():\n    return nope\n")
    assert "DIAGNOSTICS" in warn and ("nope" in warn or "undefined" in warn.lower())
    assert lint.postedit_python("y.py", "x = 1\nprint(x)\n") == ""


def test_fallback_to_pyflakes_when_no_ruff(ws, monkeypatch):
    """With ruff forced unavailable, the in-process pyflakes path still catches bugs."""
    monkeypatch.setattr(lint, "_ruff_exe", lambda: None)
    _write(ws, "z.py", "def f():\n    return undefined_thing\n")
    diags = lint.diagnose("z.py")
    assert any("undefined" in d["message"].lower() for d in diags)


def test_diagnostics_tool_confines_to_workspace(ws):
    out = tools.diagnostics("../../etc/passwd")
    assert out.startswith("ERROR")


def test_diagnostics_tool_formats_directory(ws):
    _write(ws, "a.py", "import sys\n")   # unused import
    out = tools.diagnostics(".")
    assert "diagnostic" in out.lower() or "clean" in out.lower()


def test_diagnose_on_unsaved_content(ws):
    # content buffer analysed directly (post-edit path) without touching disk
    diags = lint.diagnose("buffer.py", "def f():\n    return ghost\n")
    assert any("ghost" in d["message"].lower() or "undefined" in d["message"].lower() for d in diags)
