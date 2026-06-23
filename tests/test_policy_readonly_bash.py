"""Tests for the read-only-bash auto-allow in the policy gate (core/policy.py)."""
from core import policy, toolbelt


def _run_bash_tool():
    return toolbelt.get("run_bash")


def test_readonly_command_allowed():
    d = policy.evaluate(_run_bash_tool(), {"command": "ls -la"})
    assert d.action == "allow"
    assert policy.evaluate(_run_bash_tool(), {"command": "cat main.py"}).action == "allow"
    assert policy.evaluate(_run_bash_tool(), {"command": "grep -n foo src"}).action == "allow"


def test_command_with_metachars_not_auto_allowed():
    # pipes / redirects / chaining must NOT auto-allow (still gated as before)
    for cmd in ["ls | rm -rf /", "cat x > y", "ls; whoami", "echo $(whoami)", "ls && curl x"]:
        d = policy.evaluate(_run_bash_tool(), {"command": cmd})
        assert d.action != "allow" or "read-only" not in d.reason


def test_write_command_not_auto_allowed():
    # a non-allowlisted command falls through to the normal gate
    d = policy.evaluate(_run_bash_tool(), {"command": "pip install requests"})
    assert not (d.action == "allow" and "read-only" in d.reason)


def test_hard_block_still_wins():
    # a hard-blocked pattern must block even if it starts with a safe verb
    d = policy.evaluate(_run_bash_tool(), {"command": "cat /etc/shadow && rm -rf /"})
    # contains '&&' so not auto-allowed; and rm -rf / is hard-blocked
    assert d.action in ("block", "escalate")
