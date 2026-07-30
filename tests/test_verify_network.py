"""Opt-in networked verify sandbox (#5): AGENT_VERIFY_NETWORK lets ONLY the verify run reach a
Docker network (e.g. a DB container) so full-stack tests can run, while the agent's general
run_bash stays isolated. Default: no network override (isolated as ever)."""
import core.orchestrator as orch
import core.tools as tools


# ---- _verify_tests threads AGENT_VERIFY_NETWORK into run_bash ----

def test_verify_tests_passes_verify_network(monkeypatch):
    monkeypatch.setenv("AGENT_VERIFY_NETWORK", "dbnet")
    seen = {}
    monkeypatch.setattr(orch, "run_bash",
                        lambda cmd, network=None: (seen.update(network=network), "exit=0\n1 passed")[1])
    orch._verify_tests()
    assert seen["network"] == "dbnet"


def test_verify_tests_no_network_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_VERIFY_NETWORK", raising=False)
    seen = {}
    monkeypatch.setattr(orch, "run_bash",
                        lambda cmd, network=None: (seen.update(network=network), "exit=0\n1 passed")[1])
    orch._verify_tests()
    assert seen["network"] is None      # isolated by default


# ---- run_bash honours the per-call network override ----

class _Out:
    returncode = 0
    stdout = ""
    stderr = ""


def test_run_bash_uses_network_override(monkeypatch):
    monkeypatch.setenv("AGENT_BASH_DOCKER_IMAGE", "test-img")
    monkeypatch.delenv("AGENT_DISABLE_BASH", raising=False)
    captured = {}
    monkeypatch.setattr(tools.subprocess, "run", lambda argv, **k: (captured.update(argv=argv), _Out())[1])
    tools.run_bash("echo hi", network="dbnet")
    argv = captured["argv"]
    assert argv[argv.index("--network") + 1] == "dbnet"


def test_run_bash_defaults_to_env_network(monkeypatch):
    monkeypatch.setenv("AGENT_BASH_DOCKER_IMAGE", "test-img")
    monkeypatch.setenv("AGENT_BASH_DOCKER_NETWORK", "none")
    monkeypatch.delenv("AGENT_DISABLE_BASH", raising=False)
    captured = {}
    monkeypatch.setattr(tools.subprocess, "run", lambda argv, **k: (captured.update(argv=argv), _Out())[1])
    tools.run_bash("echo hi")           # no override -> env default
    argv = captured["argv"]
    assert argv[argv.index("--network") + 1] == "none"
