"""Single-agent failure salvage: a bare failure marker is reconstructed into a useful, grounded
answer from the WORKSPACE (the partial work) instead of being surfaced raw. Falls back to the raw
marker (so _final_payload adds the honest tip) when there's nothing to salvage or the call fails."""
import core.orchestrator as orch
from core.tools import using_workspace


class _Resp:
    def __init__(self, c):
        self.choices = [type("C", (), {"message": type("M", (), {"content": c})()})()]


class _B:
    spent_usd = 0.0
    max_usd = 1.0


def _boom(*a, **k):
    raise AssertionError("complete should not be called here")


def test_salvage_reconstructs_from_workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "app.py").write_text("x = 1")
    (ws / "test_app.py").write_text("def test(): pass")
    captured = {}

    def fake_complete(model, msgs, **k):
        captured["prompt"] = msgs[0]["content"]
        return _Resp("Accomplished: created app.py + a test. Incomplete: tests not run. Next: run pytest."), None

    monkeypatch.setattr(orch, "complete", fake_complete)
    with using_workspace(str(ws)):
        out = orch._salvage_single_agent("NEW REQUEST:build the app", "(stopped: iteration cap hit: 22)", _B())
    assert "app.py" in captured["prompt"] and "test_app.py" in captured["prompt"]   # grounded in real files
    assert "Accomplished" in out                                                     # substantive answer returned
    assert "iteration cap hit" not in out                                            # not the bare marker


def test_salvage_noop_on_successful_result(monkeypatch):
    monkeypatch.setattr(orch, "complete", _boom)
    assert orch._salvage_single_agent("t", "Here is the real answer.", _B()) == "Here is the real answer."


def test_salvage_returns_marker_when_no_files(tmp_path, monkeypatch):
    ws = tmp_path / "empty"
    ws.mkdir()
    monkeypatch.setattr(orch, "complete", _boom)     # no files -> never calls the model
    with using_workspace(str(ws)):
        out = orch._salvage_single_agent("t", "(stopped: cap)", _B())
    assert out == "(stopped: cap)"                    # raw marker -> _final_payload adds the tip


def test_salvage_deterministic_when_call_fails_but_files_exist(tmp_path, monkeypatch):
    # A capped run has often ALSO spent its budget, so the summariser call can't run — but partial
    # work exists. Must give a grounded, deterministic file-list recap, NOT the bare marker.
    ws = tmp_path / "ws2"
    ws.mkdir()
    (ws / "models.py").write_text("x")
    (ws / "storage.py").write_text("y")
    monkeypatch.setattr(orch, "complete",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no budget / provider down")))
    with using_workspace(str(ws)):
        out = orch._salvage_single_agent("t", "(stopped: iteration cap hit: 6)", _B())
    assert not out.strip().startswith("(stopped")        # NOT the bare marker
    assert "models.py" in out and "storage.py" in out     # grounded in the real partial work
    assert "continue" in out.lower()
