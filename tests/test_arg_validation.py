"""Tests for tool-argument schema validation (core/toolbelt.py + core/agent.py)."""
from core import toolbelt
from core.agent import _run_one_tool


def _tool(name):
    return toolbelt.get(name)


def test_missing_required_rejected():
    err = toolbelt.validate_args(_tool("read_file"), {})
    assert err and "missing required" in err
    assert "path" in err


def test_wrong_container_type_rejected():
    # path is a string param; passing an object is structurally wrong.
    err = toolbelt.validate_args(_tool("read_file"), {"path": {"nested": 1}})
    assert err and "should be a string" in err


def test_valid_args_pass():
    assert toolbelt.validate_args(_tool("read_file"), {"path": "a.py"}) is None
    assert toolbelt.validate_args(_tool("edit_file"),
                                  {"path": "a.py", "old_string": "x", "new_string": "y"}) is None


def test_scalar_drift_is_lenient():
    # number-as-string for offset should NOT be rejected (lenient on scalars).
    assert toolbelt.validate_args(_tool("read_file"), {"path": "a.py", "offset": "4"}) is None


def test_non_dict_args_rejected():
    assert toolbelt.validate_args(_tool("read_file"), ["a.py"]) is not None


def test_run_one_tool_returns_invalid_args_message():
    # End-to-end through the choke point: a bad call is rejected, not executed.
    out = _run_one_tool("read_file", {}, "tester", approve=None, emit=None)
    assert out.startswith("INVALID_ARGS")
    assert "read_file" in out
