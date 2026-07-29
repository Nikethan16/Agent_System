"""Tests for the leaked-raw-tool-call detector (core/agent.py, orchestration #1).

Critically: prove it does NOT clobber a legitimate answer that merely quotes
tool-call syntax (docs about function calling).
"""
from core.agent import _looks_like_raw_toolcall


# ---- must DETECT (these are leaks that must not be shown as final) ----------

def test_detects_deepseek_special_token():
    assert _looks_like_raw_toolcall("<｜DSML｜tool_calls>run_bash{...}")


def test_detects_tool_call_tag_at_start():
    assert _looks_like_raw_toolcall("<tool_call><function=run_bash>ls</function></tool_call>")


def test_detects_function_tag_at_start():
    assert _looks_like_raw_toolcall("<function=run_shell>{\"command\": \"ls\"}")


# ---- must PASS THROUGH (legitimate answers that mention the syntax) ---------

def test_passes_function_mention_in_prose():
    txt = ("To call a tool the model emits a `<function=name>` tag. Here we explain "
           "how function calling works in practice and when to use it.")
    assert not _looks_like_raw_toolcall(txt)


def test_passes_function_in_code_block():
    txt = ("Here is the format:\n\n```xml\n<tool_call><function=foo>...</function>\n```\n\n"
           "That is how providers represent a call.")
    assert not _looks_like_raw_toolcall(txt)


def test_passes_normal_answer():
    assert not _looks_like_raw_toolcall("The capital of France is Paris.")


def test_passes_empty():
    assert not _looks_like_raw_toolcall("")
    assert not _looks_like_raw_toolcall(None)


# ---- last-resort markup stripping (regression fix) -------------------------
from core.agent import _strip_toolcall_markup


def test_strip_removes_markup():
    assert "<tool_call>" not in _strip_toolcall_markup("<tool_call>hello</tool_call>")
    assert "<function=" not in _strip_toolcall_markup("<function=run>x</function> done")
    assert _strip_toolcall_markup("plain answer") == "plain answer"


# ---- regression: the DOUBLE full-width pipe DSML form that leaked from a live LEAD run ----

def test_detects_double_pipe_dsml_toolcall():
    # A live tier-3 LEAD run ended with prose + this block; the single-pipe-only regex missed it.
    leaked = ('Now I have the full picture. Let me write the synthesis.\n\n'
              '<｜｜DSML｜｜tool_calls>\n<｜｜DSML｜｜invoke name="write_todos">')
    assert _looks_like_raw_toolcall(leaked)


def test_detects_double_pipe_dsml_at_start():
    assert _looks_like_raw_toolcall("<｜｜DSML｜｜tool_calls>run_bash{}")


def test_strip_cuts_trailing_dsml_block_keeps_prose():
    leaked = ('Now I have the full picture. Let me write the synthesis.\n\n'
              '<｜｜DSML｜｜tool_calls>\n<｜｜DSML｜｜invoke name="write_todos">\n'
              '[{"content": "x", "status": "done"}]')
    cleaned = _strip_toolcall_markup(leaked)
    assert cleaned == "Now I have the full picture. Let me write the synthesis."
    assert "DSML" not in cleaned and "write_todos" not in cleaned
