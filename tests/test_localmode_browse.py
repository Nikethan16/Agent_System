"""localmode.browse powers the New Project folder picker. It MUST stay confined to
AGENT_LOCAL_ROOT: a path above/outside the root snaps back to it, and the root can't ascend.
"""
import os
from server import localmode


def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_LOCAL_MODE", "1")
    monkeypatch.setenv("AGENT_LOCAL_ROOT", str(tmp_path))
    (tmp_path / "proj" / ".git").mkdir(parents=True)   # looks like a repo
    (tmp_path / "sub" / "deep").mkdir(parents=True)


def test_disabled_returns_error(monkeypatch):
    monkeypatch.delenv("AGENT_LOCAL_MODE", raising=False)
    ok, _ = localmode.browse("")
    assert ok is False


def test_lists_root_with_repo_flag(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    ok, p = localmode.browse("")
    assert ok
    names = {d["name"]: d for d in p["dirs"]}
    assert names["proj"]["is_repo"] is True
    assert names["sub"]["is_repo"] is False
    assert p["parent"] == ""                            # root can't ascend above itself


def test_descend_sets_parent_to_root(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    ok, p = localmode.browse(str(tmp_path / "sub"))
    assert ok and p["parent"] == localmode.allowed_root()


def test_escape_above_root_snaps_back(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    ok, p = localmode.browse(str(tmp_path.parent))      # a dir ABOVE the allowed root
    assert ok and p["path"] == localmode.allowed_root()
