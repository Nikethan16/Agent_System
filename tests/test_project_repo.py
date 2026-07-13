"""Project-from-repo: creating a project with a Git URL clones the repo into the
project's shared workspace, stores the origin, and exposes git status. clone_into is
mocked (no network) except the guard tests, which fail before any network call."""
import os
import shutil
import tempfile

from server import db, projects
from tools import github as gh

db.init_db()


def _cleanup(pid):
    shutil.rmtree(db.project_workspace(pid), ignore_errors=True)
    projects.delete(pid)


def test_create_from_repo_success(monkeypatch):
    def fake_clone(url, dest, branch=""):
        open(os.path.join(dest, "README.md"), "w").close()   # simulate a cloned file
        os.makedirs(os.path.join(dest, ".git"), exist_ok=True)
        return True, "Cloning into '.'..."
    monkeypatch.setattr(gh, "clone_into", fake_clone)
    p = projects.create_from_repo("repo-proj", "https://github.com/me/app.git", "main")
    try:
        assert p["clone"]["ok"] is True
        assert p["repo_url"] == "https://github.com/me/app.git"
        assert os.path.exists(os.path.join(db.project_workspace(p["id"]), "README.md"))
    finally:
        _cleanup(p["id"])


def test_create_from_repo_refuses_nonempty_workspace(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(gh, "clone_into", lambda *a, **k: (called.__setitem__("n", called["n"] + 1), (True, ""))[1])
    p = projects.create("pre-existing")
    try:
        # Put a file in the workspace BEFORE cloning -> create_from_repo must refuse.
        ws = db.project_workspace(p["id"])
        open(os.path.join(ws, "keep.txt"), "w").close()
        # Re-run the repo path against the SAME project id by monkeypatching create to return it.
        monkeypatch.setattr(projects, "create", lambda name="New project": projects.get(p["id"]))
        r = projects.create_from_repo("x", "https://github.com/me/app.git")
        assert r["clone"]["ok"] is False and "not empty" in r["clone"]["message"]
        assert called["n"] == 0                              # never attempted the clone
    finally:
        _cleanup(p["id"])


def test_repo_info_non_git():
    p = projects.create("plain")
    try:
        assert projects.repo_info(p["id"]) == {"repo": False}
    finally:
        _cleanup(p["id"])


def test_clone_into_guards_bad_urls():
    d = tempfile.mkdtemp()
    try:
        assert gh.clone_into("ftp://x/y", d)[0] is False              # bad scheme
        assert gh.clone_into("http://127.0.0.1/x.git", d)[0] is False  # SSRF loopback
        assert gh.clone_into("http://169.254.169.254/x", d)[0] is False  # cloud metadata
    finally:
        shutil.rmtree(d, ignore_errors=True)
