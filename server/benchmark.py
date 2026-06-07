"""
benchmark.py — the "Model Lab": score a model on the benchmark battery and store
results so you can compare models and pick the right one per task.

The actual run happens in an isolated SUBPROCESS (scripts/run_benchmark.py) so it
can pin the model + use a scratch workspace without disturbing the live app. This
module owns the DB record, spawns the subprocess in a background thread, and stores
the resulting scorecard.
"""
import os
import sys
import json
import tempfile
import threading
import subprocess

import yaml
from sqlmodel import SQLModel, Field, Session as DBSession, select

from .db import engine, _uuid, _now

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_ROOT, "scripts", "run_benchmark.py")
_SUITE = os.path.join(_ROOT, "evals", "benchmark.yaml")

_lock = threading.Lock()
_running = {"on": False}


class BenchmarkRun(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    model: str = ""
    mode: str = "both"             # raw | pipeline | both
    status: str = "running"        # running | done | error
    result: str = "{}"             # JSON scorecard
    cost: float = 0.0
    error: str = ""
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


def aspects() -> dict:
    """Aspect -> task count, for the UI."""
    with open(_SUITE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    out: dict = {}
    for c in data.get("cases", []) or []:
        out[c.get("aspect", "other")] = out.get(c.get("aspect", "other"), 0) + 1
    return out


def _model_available(model: str) -> bool:
    """If the model is in the catalog, require its provider key to be set."""
    from core.registry import registry
    for m in registry.catalog():
        if m.get("id") == model:
            env = m.get("requires_env")
            return (not env) or bool(os.environ.get(env))
    return True   # unknown model id -> let the run try (and surface any error)


def _finish(rid, status, result, cost, error=""):
    with DBSession(engine) as s:
        r = s.get(BenchmarkRun, rid)
        if r:
            r.status, r.result = status, json.dumps(result)
            r.cost, r.error, r.updated_at = round(cost or 0.0, 6), error, _now()
            s.add(r)
            s.commit()


def start_run(model: str, mode: str = "both", dry_run: bool = False) -> str:
    model = (model or "").strip()
    if not model:
        raise ValueError("model is required")
    if mode not in ("raw", "pipeline", "both"):
        mode = "both"
    with DBSession(engine) as s:
        run = BenchmarkRun(model=model, mode=mode, status="running")
        s.add(run)
        s.commit()
        s.refresh(run)
        rid = run.id

    def worker():
        with _lock:
            if _running["on"]:
                _finish(rid, "error", {}, 0.0, "another benchmark is already running")
                return
            _running["on"] = True
        try:
            if not dry_run and not _model_available(model):
                _finish(rid, "error", {}, 0.0, f"provider key for {model} is not set")
                return
            out_path = os.path.join(tempfile.gettempdir(), f"bench_{rid}.json")
            cmd = [sys.executable, _SCRIPT, "--model", model, "--mode", mode, "--out", out_path]
            if dry_run:
                cmd.append("--dry-run")
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=_ROOT)
            if not os.path.isfile(out_path):
                tail = (proc.stderr or proc.stdout or "")[-400:]
                _finish(rid, "error", {}, 0.0, f"benchmark process produced no result. {tail}")
                return
            with open(out_path, encoding="utf-8") as f:
                result = json.load(f)
            os.remove(out_path)
            status = "error" if result.get("error") else "done"
            _finish(rid, status, result, result.get("cost", 0.0), result.get("error", ""))
        except subprocess.TimeoutExpired:
            _finish(rid, "error", {}, 0.0, "benchmark timed out (30 min)")
        except Exception as e:
            _finish(rid, "error", {}, 0.0, f"{type(e).__name__}: {e}")
        finally:
            with _lock:
                _running["on"] = False

    threading.Thread(target=worker, daemon=True).start()
    return rid


def _row(r: BenchmarkRun) -> dict:
    try:
        result = json.loads(r.result or "{}")
    except Exception:
        result = {}
    return {"id": r.id, "model": r.model, "mode": r.mode, "status": r.status,
            "result": result, "cost": r.cost, "error": r.error,
            "created_at": r.created_at, "updated_at": r.updated_at}


def list_runs() -> list:
    with DBSession(engine) as s:
        rows = s.exec(select(BenchmarkRun).order_by(BenchmarkRun.created_at.desc())).all()
        return [_row(r) for r in rows]


def get_run(run_id: str):
    with DBSession(engine) as s:
        r = s.get(BenchmarkRun, run_id)
        return _row(r) if r else None
