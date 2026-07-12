"""The disk janitor reclaims ORPHANED (session gone) and AGED trace/checkpoint data,
never touches live-recent data, and only removes workspaces when explicitly asked.
Runs against a synthetic data dir (tmp_path) — no real files, no DB, no docker."""
import os
import time

from scripts import cleanup


def _touch(path, age_days=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("x")
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))


def _mkdir(path, age_days=0):
    os.makedirs(path, exist_ok=True)
    _touch(os.path.join(path, "f"), age_days)
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))


def _wire(monkeypatch, tmp_path, live_ids):
    traces = str(tmp_path / "traces")
    cps = str(tmp_path / "checkpoints")
    ws = str(tmp_path / "workspaces")
    monkeypatch.setattr(cleanup, "_TRACES", traces)
    monkeypatch.setattr(cleanup, "_CHECKPOINTS", cps)
    monkeypatch.setattr(cleanup, "_WORKSPACES", ws)
    monkeypatch.setattr(cleanup, "_live_session_ids", lambda: set(live_ids))
    return traces, cps, ws


def test_traces_orphaned_removed_live_recent_kept(monkeypatch, tmp_path):
    traces, _cps, _ws = _wire(monkeypatch, tmp_path, live_ids={"live"})
    _touch(os.path.join(traces, "live.jsonl"), age_days=0)      # live + recent -> KEEP
    _touch(os.path.join(traces, "orphan.jsonl"), age_days=0)    # session gone -> DROP
    cleanup.sweep(days=30, dry_run=False, log=lambda *_: None)
    remaining = set(os.listdir(traces))
    assert "live.jsonl" in remaining
    assert "orphan.jsonl" not in remaining


def test_live_but_aged_trace_is_removed(monkeypatch, tmp_path):
    traces, _cps, _ws = _wire(monkeypatch, tmp_path, live_ids={"s1"})
    _touch(os.path.join(traces, "s1.jsonl"), age_days=99)       # live BUT aged -> DROP
    cleanup.sweep(days=30, dry_run=False, log=lambda *_: None)
    assert "s1.jsonl" not in set(os.listdir(traces))


def test_dry_run_deletes_nothing(monkeypatch, tmp_path):
    traces, _cps, _ws = _wire(monkeypatch, tmp_path, live_ids=set())
    _touch(os.path.join(traces, "orphan.jsonl"), age_days=99)
    items, freed = cleanup.sweep(days=30, dry_run=True, log=lambda *_: None)
    assert items == 1 and freed > 0
    assert os.path.exists(os.path.join(traces, "orphan.jsonl"))   # still there


def test_checkpoints_orphan_dropped_live_aged_out(monkeypatch, tmp_path):
    _traces, cps, _ws = _wire(monkeypatch, tmp_path, live_ids={"s1"})
    _mkdir(os.path.join(cps, "gone", "cp1"))                    # orphan session -> whole tree DROP
    _mkdir(os.path.join(cps, "s1", "recent"), age_days=0)       # live + recent -> KEEP
    _mkdir(os.path.join(cps, "s1", "ancient"), age_days=99)     # live + aged -> DROP
    cleanup.sweep(days=30, dry_run=False, log=lambda *_: None)
    assert not os.path.exists(os.path.join(cps, "gone"))
    assert os.path.exists(os.path.join(cps, "s1", "recent"))
    assert not os.path.exists(os.path.join(cps, "s1", "ancient"))


def test_workspaces_only_touched_when_requested(monkeypatch, tmp_path):
    _traces, _cps, ws = _wire(monkeypatch, tmp_path, live_ids={"s1"})
    _mkdir(os.path.join(ws, "s1"))                 # live -> KEEP
    _mkdir(os.path.join(ws, "orphan"))             # session gone -> DROP (only with flag)
    _mkdir(os.path.join(ws, "project_abc"))        # shared project -> ALWAYS KEEP
    _mkdir(os.path.join(ws, "_bench_ws"))          # internal -> ALWAYS KEEP

    # Default sweep must NOT touch workspaces at all.
    cleanup.sweep(days=30, workspaces=False, dry_run=False, log=lambda *_: None)
    assert os.path.exists(os.path.join(ws, "orphan"))

    # With --workspaces: only the orphan goes; project/live/internal stay.
    cleanup.sweep(days=30, workspaces=True, dry_run=False, log=lambda *_: None)
    assert not os.path.exists(os.path.join(ws, "orphan"))
    assert os.path.exists(os.path.join(ws, "s1"))
    assert os.path.exists(os.path.join(ws, "project_abc"))
    assert os.path.exists(os.path.join(ws, "_bench_ws"))


def test_orphan_pruning_skipped_when_db_unreadable(monkeypatch, tmp_path):
    """If the session list can't be read, ORPHAN pruning is skipped (age-only) — never
    guess-and-delete. An orphaned-but-recent trace must survive."""
    traces = str(tmp_path / "traces")
    monkeypatch.setattr(cleanup, "_TRACES", traces)
    monkeypatch.setattr(cleanup, "_CHECKPOINTS", str(tmp_path / "cp"))
    monkeypatch.setattr(cleanup, "_WORKSPACES", str(tmp_path / "ws"))
    monkeypatch.setattr(cleanup, "_live_session_ids", lambda: None)   # DB unreadable
    _touch(os.path.join(traces, "recent.jsonl"), age_days=0)
    cleanup.sweep(days=30, dry_run=False, log=lambda *_: None)
    assert os.path.exists(os.path.join(traces, "recent.jsonl"))       # kept (not aged, orphans skipped)
