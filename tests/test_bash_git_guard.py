"""run_bash must redirect NETWORK git ops (clone/push/pull/fetch) to the dedicated
host-side git_* tools — the sandbox has an isolated network, a read-only fs, and no
credentials, so in-container `git clone` can only fail (live e2e: 19 wasted bash calls).
Local git (status/log/diff/commit) stays allowed."""
import pytest

from core import tools as ctools


BLOCKED = [
    "git clone https://github.com/octocat/Hello-World.git",
    "cd /ws && git clone https://github.com/a/b.git repo",
    "git push origin main",
    "git pull",
    "git fetch origin",
    "git -C /ws clone https://github.com/a/b",     # option between git and verb
]

ALLOWED = [
    "git status",
    "git log --oneline -5",
    "git diff HEAD~1",
    "git commit -m 'msg'",
    "echo cloned && ls",                            # word 'cloned' isn't the git verb
    "pip install gitpython",
]


@pytest.mark.parametrize("cmd", BLOCKED)
def test_network_git_blocked(cmd, monkeypatch):
    monkeypatch.delenv("AGENT_DISABLE_BASH", raising=False)
    out = ctools.run_bash(cmd)
    assert out.startswith("BLOCKED"), (cmd, out[:80])
    assert "git_clone" in out                       # points at the right tool


@pytest.mark.parametrize("cmd", ALLOWED)
def test_local_git_and_other_commands_not_blocked(cmd, monkeypatch):
    monkeypatch.delenv("AGENT_DISABLE_BASH", raising=False)
    monkeypatch.delenv("AGENT_BASH_DOCKER_IMAGE", raising=False)
    out = ctools.run_bash(cmd)
    # Without a Docker image these fall through to the no-image ERROR — the point is
    # they must NOT hit the network-git BLOCKED path.
    assert not out.startswith("BLOCKED"), (cmd, out[:80])
