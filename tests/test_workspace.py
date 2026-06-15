"""Unit tests for server/api/workspace.py — _line_counts() and compute_changes()."""
import os
import pytest

from server.api.workspace import _line_counts, compute_changes
import server.db as db


class TestLineCounts:
    def test_identical_content(self):
        a, r = _line_counts("hello\nworld\n", "hello\nworld\n")
        assert a == 0 and r == 0

    def test_pure_addition(self):
        a, r = _line_counts("", "line1\nline2\n")
        assert a == 2 and r == 0

    def test_pure_deletion(self):
        a, r = _line_counts("line1\nline2\n", "")
        assert a == 0 and r == 2

    def test_modification(self):
        a, r = _line_counts("hello\nworld\n", "hello\nnew world\nadded\n")
        assert a == 2 and r == 1

    def test_empty_to_empty(self):
        a, r = _line_counts("", "")
        assert a == 0 and r == 0


class TestComputeChanges:
    def test_no_checkpoint_returns_empty(self, monkeypatch):
        monkeypatch.setattr(db, "latest_checkpoint_dir", lambda _: None)
        monkeypatch.setattr(db, "session_workspace", lambda _: "/tmp")
        assert compute_changes("fakeid") == []

    def test_added_file(self, tmp_path, monkeypatch):
        ws = tmp_path / "ws"
        cp = tmp_path / "cp"
        ws.mkdir(); cp.mkdir()
        (ws / "new.py").write_text("line1\nline2\n")
        monkeypatch.setattr(db, "latest_checkpoint_dir", lambda _: str(cp))
        monkeypatch.setattr(db, "session_workspace", lambda _: str(ws))
        changes = compute_changes("fakeid")
        assert len(changes) == 1
        assert changes[0]["path"] == "new.py"
        assert changes[0]["status"] == "added"
        assert changes[0]["added"] == 2
        assert changes[0]["removed"] == 0

    def test_deleted_file(self, tmp_path, monkeypatch):
        ws = tmp_path / "ws"
        cp = tmp_path / "cp"
        ws.mkdir(); cp.mkdir()
        (cp / "old.py").write_text("gone\n")
        monkeypatch.setattr(db, "latest_checkpoint_dir", lambda _: str(cp))
        monkeypatch.setattr(db, "session_workspace", lambda _: str(ws))
        changes = compute_changes("fakeid")
        assert changes[0]["status"] == "deleted"
        assert changes[0]["removed"] == 1
        assert changes[0]["added"] == 0

    def test_modified_file_with_counts(self, tmp_path, monkeypatch):
        ws = tmp_path / "ws"
        cp = tmp_path / "cp"
        ws.mkdir(); cp.mkdir()
        (cp / "f.py").write_text("a\nb\nc\n")
        (ws / "f.py").write_text("a\nB\nc\nd\n")
        monkeypatch.setattr(db, "latest_checkpoint_dir", lambda _: str(cp))
        monkeypatch.setattr(db, "session_workspace", lambda _: str(ws))
        changes = compute_changes("fakeid")
        assert changes[0]["status"] == "modified"
        assert changes[0]["added"] == 2   # B and d
        assert changes[0]["removed"] == 1  # b

    def test_unchanged_file_not_reported(self, tmp_path, monkeypatch):
        ws = tmp_path / "ws"
        cp = tmp_path / "cp"
        ws.mkdir(); cp.mkdir()
        content = "same\n"
        (cp / "same.py").write_text(content)
        (ws / "same.py").write_text(content)
        monkeypatch.setattr(db, "latest_checkpoint_dir", lambda _: str(cp))
        monkeypatch.setattr(db, "session_workspace", lambda _: str(ws))
        assert compute_changes("fakeid") == []
