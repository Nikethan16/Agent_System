"""Local-folder mode: OFF by default; when AGENT_LOCAL_MODE=1 a project can bind to a
real dir INSIDE AGENT_LOCAL_ROOT (realpath, no symlink/`..` escape), and its sessions
resolve to that dir. Disabling the flag instantly stops serving the local path."""
import os

from server import db, projects, localmode


def _enable(monkeypatch, root):
    monkeypatch.setenv("AGENT_LOCAL_MODE", "1")
    monkeypatch.setenv("AGENT_LOCAL_ROOT", str(root))


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_LOCAL_MODE", raising=False)
    assert localmode.enabled() is False
    ok, msg = localmode.validate_path("/anything")
    assert ok is False and "disabled" in msg


def test_validate_confines_to_root(monkeypatch, tmp_path):
    inside = tmp_path / "repo"
    inside.mkdir()
    _enable(monkeypatch, tmp_path)
    ok, resolved = localmode.validate_path(str(inside))
    assert ok and os.path.realpath(str(inside)) == resolved
    # outside the root -> refused
    ok2, msg2 = localmode.validate_path(str(tmp_path.parent))
    assert ok2 is False and "inside" in msg2
    # non-existent dir inside root -> refused
    ok3, msg3 = localmode.validate_path(str(inside / "missing"))
    assert ok3 is False and "directory" in msg3


def test_create_local_binds_workspace(monkeypatch, tmp_path):
    folder = tmp_path / "myapp"
    folder.mkdir()
    (folder / "main.py").write_text("print('real file')", encoding="utf-8")
    _enable(monkeypatch, tmp_path)
    db.init_db()

    p = projects.create_local("Local App", str(folder))
    try:
        assert p.get("local", {}).get("ok") is True
        assert p["local_path"] == os.path.realpath(str(folder))
        # project_workspace resolves to the REAL folder (not data/workspaces/…)
        assert db.project_workspace(p["id"]) == os.path.realpath(str(folder))
        # a session in the project shares that same real workspace
        s = db.create_session("s1", project_id=p["id"])
        assert db.session_workspace(s.id) == os.path.realpath(str(folder))
    finally:
        projects.delete(p["id"])


def test_disabling_flag_stops_serving_local_path(monkeypatch, tmp_path):
    folder = tmp_path / "app2"
    folder.mkdir()
    _enable(monkeypatch, tmp_path)
    db.init_db()
    p = projects.create_local("L2", str(folder))
    try:
        assert db.project_workspace(p["id"]) == os.path.realpath(str(folder))
        # turn the feature OFF -> workspace falls back to the sandboxed copy, NOT the real dir
        monkeypatch.delenv("AGENT_LOCAL_MODE", raising=False)
        ws = db.project_workspace(p["id"])
        assert ws != os.path.realpath(str(folder))
        assert "workspaces" in ws
    finally:
        projects.delete(p["id"])


def test_create_local_refused_when_disabled(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENT_LOCAL_MODE", raising=False)
    db.init_db()
    r = projects.create_local("nope", str(tmp_path))
    assert "error" in r and "disabled" in r["error"]
