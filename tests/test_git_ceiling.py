"""Git tools must NEVER escape the workspace upward. Session workspaces live inside the
app's own git checkout on the server, and git's repo discovery walks parent directories —
live e2e saw git_log in a fresh workspace report the APP repo's commits. _git now sets
GIT_CEILING_DIRECTORIES to the workspace's parent, so discovery stops at the workspace.
"""
import os
import subprocess

import pytest

from core import tools as ctools
import tools.github as gh


def _make_outer_repo(tmp_path):
    outer = tmp_path / "outer"
    ws = outer / "data" / "workspaces" / "session1"
    ws.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(outer)], check=True)
    subprocess.run(["git", "-C", str(outer), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(outer), "config", "user.name", "t"], check=True)
    (outer / "app.py").write_text("print('app')\n")
    subprocess.run(["git", "-C", str(outer), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(outer), "commit", "-qm", "outer-repo-commit"], check=True)
    return outer, ws


def test_git_log_does_not_walk_up_to_outer_repo(tmp_path):
    outer, ws = _make_outer_repo(tmp_path)
    with ctools.using_workspace(str(ws)):
        out = gh.git_log(3)
    assert "outer-repo-commit" not in out          # must NOT see the app repo's history
    assert "exit=0" not in out.split("\n")[0]      # a non-repo workspace errors instead


def test_git_status_confined(tmp_path):
    outer, ws = _make_outer_repo(tmp_path)
    with ctools.using_workspace(str(ws)):
        out = gh.git_status()
    assert not out.startswith("exit=0")


def test_real_repo_inside_workspace_still_works(tmp_path):
    _, ws = _make_outer_repo(tmp_path)
    subprocess.run(["git", "init", "-q", str(ws)], check=True)
    subprocess.run(["git", "-C", str(ws), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(ws), "config", "user.name", "t"], check=True)
    (ws / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(ws), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(ws), "commit", "-qm", "inner-commit"], check=True)
    with ctools.using_workspace(str(ws)):
        out = gh.git_log(3)
    assert out.startswith("exit=0") and "inner-commit" in out
