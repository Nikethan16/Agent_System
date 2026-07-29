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
