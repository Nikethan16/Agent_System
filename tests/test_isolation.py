"""Local-project isolation: the agent works on a COPY; approved changes merge back — a git
repo as a NON-DESTRUCTIVE branch (the user's working tree is untouched until they merge it),
a non-git folder by copying changed files over."""
import os
import subprocess

from server import isolation


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _make_git_repo(path):
    os.makedirs(path, exist_ok=True)
    _git(["init", "-q"], path)
    _git(["config", "user.email", "t@e"], path)
    _git(["config", "user.name", "t"], path)
    with open(os.path.join(path, "app.py"), "w") as f:
        f.write("x = 1\n")
    _git(["add", "-A"], path)
    _git(["commit", "-qm", "init"], path)


def test_git_repo_merges_as_branch_without_touching_worktree(tmp_path):
    real = str(tmp_path / "real")
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    _make_git_repo(real)

    # 1) work copy is a real clone of the repo
    copy = isolation.ensure_work_copy("p1", real, ws)
    assert os.path.isdir(os.path.join(copy, ".git"))
    assert os.path.exists(os.path.join(copy, "app.py"))

    # 2) the agent edits the COPY (change a file + add a new one)
    with open(os.path.join(copy, "app.py"), "w") as f:
        f.write("x = 42\n")
    with open(os.path.join(copy, "new.py"), "w") as f:
        f.write("y = 2\n")
    assert isolation.has_changes("p1", real, ws)

    # 3) the REAL working tree is still untouched
    assert open(os.path.join(real, "app.py")).read() == "x = 1\n"
    assert not os.path.exists(os.path.join(real, "new.py"))

    # 4) merge -> a branch appears in the real repo, but its working tree STILL doesn't change
    res = isolation.merge_to_real("p1", real, ws, label="my change")
    assert res["ok"] and res["mode"] == "git-branch"
    branch = res["branch"]
    assert branch.startswith("nikki/")
    branches = _git(["branch", "--list", branch], real).stdout
    assert branch in branches                                   # branch landed in real repo
    assert open(os.path.join(real, "app.py")).read() == "x = 1\n"   # worktree untouched
    # the branch actually contains the change
    show = _git(["show", f"{branch}:app.py"], real).stdout
    assert "x = 42" in show
    assert "y = 2" in _git(["show", f"{branch}:new.py"], real).stdout


def test_non_git_folder_copies_changed_files_over(tmp_path):
    real = str(tmp_path / "real")
    ws = str(tmp_path / "ws")
    os.makedirs(real)
    os.makedirs(ws)
    with open(os.path.join(real, "notes.txt"), "w") as f:
        f.write("original\n")

    copy = isolation.ensure_work_copy("p2", real, ws)
    assert not os.path.isdir(os.path.join(copy, ".git"))        # plain copy, no git
    with open(os.path.join(copy, "notes.txt"), "w") as f:
        f.write("edited\n")

    res = isolation.merge_to_real("p2", real, ws, label="edit")
    assert res["ok"] and res["mode"] == "copy"
    assert open(os.path.join(real, "notes.txt")).read() == "edited\n"


def test_isolation_toggle(monkeypatch):
    monkeypatch.setenv("AGENT_LOCAL_ISOLATED", "1")
    assert isolation.is_enabled() is True
    monkeypatch.setenv("AGENT_LOCAL_ISOLATED", "0")
    assert isolation.is_enabled() is False
    monkeypatch.delenv("AGENT_LOCAL_ISOLATED", raising=False)
    assert isolation.is_enabled() is False                       # OPT-IN: default OFF


def test_work_copy_is_reused_across_turns(tmp_path):
    real = str(tmp_path / "real")
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    _make_git_repo(real)
    c1 = isolation.ensure_work_copy("p3", real, ws)
    with open(os.path.join(c1, "marker.txt"), "w") as f:
        f.write("kept\n")
    c2 = isolation.ensure_work_copy("p3", real, ws)              # 2nd turn
    assert c1 == c2 and os.path.exists(os.path.join(c2, "marker.txt"))   # not re-cloned
