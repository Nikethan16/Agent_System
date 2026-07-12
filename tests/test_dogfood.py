"""Tests for the dogfood harness logic (scripts/dogfood.py) — the non-LLM parts."""
import os

from scripts import dogfood


def test_seed_creates_files_and_seed_is_green(tmp_path):
    ws = str(tmp_path / "proj")
    dogfood.seed_project(ws)
    assert dogfood.verify_seed(ws)
    # the seeded project's own tests must pass — the baseline the agent starts from
    assert dogfood._run_pytest(ws) is True


def test_check_result_true_when_feature_added(tmp_path):
    ws = str(tmp_path / "proj")
    dogfood.seed_project(ws)
    # simulate the agent's edit: add multiply + a test
    with open(os.path.join(ws, "calc.py"), "a", encoding="utf-8") as f:
        f.write("\n\ndef multiply(a, b):\n    return a * b\n")
    with open(os.path.join(ws, "test_calc.py"), "a", encoding="utf-8") as f:
        f.write("\n\ndef test_multiply():\n    assert calc.multiply(3, 4) == 12\n")
    assert dogfood.check_result(ws) is True


def test_check_result_false_on_bare_seed(tmp_path):
    ws = str(tmp_path / "proj")
    dogfood.seed_project(ws)
    # no multiply added → the feature check must fail
    assert dogfood.check_result(ws) is False


def test_check_result_false_when_tests_break(tmp_path):
    ws = str(tmp_path / "proj")
    dogfood.seed_project(ws)
    # multiply present but the test asserts something wrong → pytest fails → overall False
    with open(os.path.join(ws, "calc.py"), "a", encoding="utf-8") as f:
        f.write("\n\ndef multiply(a, b):\n    return a * b\n")
    with open(os.path.join(ws, "test_calc.py"), "a", encoding="utf-8") as f:
        f.write("\n\ndef test_multiply():\n    assert calc.multiply(3, 4) == 999\n")
    assert dogfood.check_result(ws) is False
