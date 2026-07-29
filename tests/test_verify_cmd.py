"""AGENT_VERIFY_CMD lets the deterministic test-gate use a project-specific command instead of
the default `python -m pytest -q` — needed for repos whose plain pytest can't run in the sandbox
(e.g. a conftest that imports a DB stack). The gate still derives pass/fail from the REAL exit
code that run_bash returns."""
import core.orchestrator as orch


def _fake_run_bash(recorded):
    def _rb(cmd):
        recorded.append(cmd)
        return "exit=0\n32 passed in 1.02s"
    return _rb


def test_default_command_when_unset(monkeypatch):
    monkeypatch.delenv("AGENT_VERIFY_CMD", raising=False)
    seen = []
    monkeypatch.setattr(orch, "run_bash", _fake_run_bash(seen))
    ran, passed, tail = orch._verify_tests()
    assert seen == ["python -m pytest -q"]
    assert ran is True and passed is True


def test_override_command_is_used(monkeypatch):
    cmd = "cd backend && python -m pytest tests/test_confidence_next_tier.py -q --noconftest"
    monkeypatch.setenv("AGENT_VERIFY_CMD", cmd)
    seen = []
    monkeypatch.setattr(orch, "run_bash", _fake_run_bash(seen))
    ran, passed, tail = orch._verify_tests()
    assert seen == [cmd]                 # the override, not the default, was run
    assert ran is True and passed is True
    assert "passed" in tail


def test_override_still_gates_on_real_exit_code(monkeypatch):
    monkeypatch.setenv("AGENT_VERIFY_CMD", "cd backend && python -m pytest -q --noconftest")
    monkeypatch.setattr(orch, "run_bash", lambda cmd: "exit=1\n1 failed, 31 passed in 1.1s")
    ran, passed, tail = orch._verify_tests()
    assert ran is True and passed is False   # a red suite is still red under the override
    assert "failed" in tail


def test_blank_override_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AGENT_VERIFY_CMD", "   ")
    seen = []
    monkeypatch.setattr(orch, "run_bash", _fake_run_bash(seen))
    orch._verify_tests()
    assert seen == ["python -m pytest -q"]


# ---- per-project .nikki/verify.txt takes precedence over the global env var ----
import os

from core.tools import using_workspace


def test_project_verify_file_wins_over_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_VERIFY_CMD", "python -m pytest -q")  # global default-ish
    ws = tmp_path / "proj"
    (ws / ".nikki").mkdir(parents=True)
    proj_cmd = "cd backend && pytest tests/test_confidence_next_tier.py -q --noconftest"
    # A leading comment + blank line must be skipped; the first real line is the command.
    (ws / ".nikki" / "verify.txt").write_text(f"# how Nikki verifies this project\n\n{proj_cmd}\n",
                                              encoding="utf-8")
    seen = []
    monkeypatch.setattr(orch, "run_bash", _fake_run_bash(seen))
    with using_workspace(str(ws)):
        orch._verify_tests()
    assert seen == [proj_cmd]            # the project file won, not the env


def test_falls_back_to_env_when_no_project_file(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_VERIFY_CMD", "custom-env-cmd")
    ws = tmp_path / "proj2"
    ws.mkdir()
    seen = []
    monkeypatch.setattr(orch, "run_bash", _fake_run_bash(seen))
    with using_workspace(str(ws)):
        orch._verify_tests()
    assert seen == ["custom-env-cmd"]
