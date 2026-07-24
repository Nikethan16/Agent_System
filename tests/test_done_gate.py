"""The done-gate (regression for the false-green critic bug found in the 2026-07-24 deep test).

The critic must NEVER report pass when a real test suite is red, and an unparseable verdict
must be treated as a FAIL (defaulting to pass is exactly how a false-green slips through).
`_verify_tests` derives pass/fail from the real pytest exit code via the sandboxed run_bash,
so we stub run_bash to canned outputs and stub the critic model call — fully offline."""
from core import orchestrator


def test_verify_tests_parses_real_exit_code(monkeypatch):
    # red suite -> (ran=True, passed=False)
    monkeypatch.setattr(orchestrator, "run_bash",
                        lambda cmd: "exit=1\nSTDOUT:\n1 failed, 22 passed in 1.1s\nSTDERR:\n")
    ran, passed, tail = orchestrator._verify_tests()
    assert ran is True and passed is False and "1 failed" in tail

    # green suite -> (ran=True, passed=True)
    monkeypatch.setattr(orchestrator, "run_bash",
                        lambda cmd: "exit=0\nSTDOUT:\n23 passed in 1.0s\nSTDERR:\n")
    ran, passed, tail = orchestrator._verify_tests()
    assert ran is True and passed is True and "23 passed" in tail

    # no tests collected (pytest exit 5) -> ran=False so callers don't block
    monkeypatch.setattr(orchestrator, "run_bash",
                        lambda cmd: "exit=5\nSTDOUT:\nno tests ran in 0.0s\nSTDERR:\n")
    ran, passed, tail = orchestrator._verify_tests()
    assert ran is False

    # no sandbox available -> ran=False (can't gate what can't run)
    monkeypatch.setattr(orchestrator, "run_bash",
                        lambda cmd: "ERROR: AGENT_BASH_DOCKER_IMAGE is not set.")
    ran, passed, tail = orchestrator._verify_tests()
    assert ran is False


def test_review_red_tests_override_model_pass(monkeypatch):
    """The model claims pass, but the real suite is red -> _review must return FALSE."""
    monkeypatch.setattr(orchestrator.team, "run",
                        lambda *a, **k: '{"pass": true, "summary": "All 23 tests pass"}')
    monkeypatch.setattr(orchestrator, "_verify_tests", lambda emit=None: (True, False, "1 failed, 22 passed"))
    passed, feedback = orchestrator._review("task", "result", budget=None, emit=None, approve=None)
    assert passed is False
    assert "NOT green" in feedback or "1 failed" in feedback


def test_review_unparseable_verdict_is_fail(monkeypatch):
    """A verdict we can't parse must be a FAIL, not a default pass."""
    monkeypatch.setattr(orchestrator.team, "run", lambda *a, **k: "the model rambled with no json")
    monkeypatch.setattr(orchestrator, "_verify_tests", lambda emit=None: (False, True, ""))
    passed, feedback = orchestrator._review("task", "result", budget=None, emit=None, approve=None)
    assert passed is False


def test_review_green_tests_and_model_pass_is_pass(monkeypatch):
    monkeypatch.setattr(orchestrator.team, "run",
                        lambda *a, **k: '{"pass": true, "summary": "looks good"}')
    monkeypatch.setattr(orchestrator, "_verify_tests", lambda emit=None: (True, True, "23 passed"))
    passed, feedback = orchestrator._review("task", "result", budget=None, emit=None, approve=None)
    assert passed is True
