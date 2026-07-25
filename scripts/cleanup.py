"""
cleanup.py — the disk janitor. Reclaims the data that grows UNBOUNDED on a 24/7 host.

What actually accumulates (and what this prunes):
  * data/traces/<session>.jsonl   — one observability log per session, never capped.
  * data/checkpoints/<session>/…  — pre-turn workspace snapshots (already capped at
                                     MAX_CHECKPOINTS per LIVE session, but whole dirs
                                     linger after a session is deleted).
  * data/workspaces/<session>     — agent-generated files (USER DATA — opt-in only).
  * dangling docker images        — the old `agent-verify:latest` left after a rebuild.

Two removal rules, both conservative:
  ORPHANED  — the owning session no longer exists in the DB → dead weight, always safe.
  AGED      — a trace/checkpoint older than --days (default 30) → rarely reopened.

Workspaces hold files the user may still want, so they are NEVER touched unless you
pass --workspaces (and only orphaned ones even then). Docker pruning is opt-in too.

    python scripts/cleanup.py                 # safe sweep: orphaned + aged traces/checkpoints
    python scripts/cleanup.py --dry-run       # show what WOULD be freed, delete nothing
    python scripts/cleanup.py --days 14       # age threshold
    python scripts/cleanup.py --workspaces    # ALSO remove orphaned session workspaces
    python scripts/cleanup.py --docker        # ALSO `docker image prune -f` (dangling)
    python scripts/cleanup.py --all           # everything above

The server also runs the SAFE sweep (orphaned + aged traces/checkpoints, no workspaces,
no docker) once in the background at startup, so the box self-maintains without a cron.
Set AGENT_DISABLE_JANITOR=1 to turn that off.
"""
import os
import stat
import sys
import time
import shutil
import argparse
import subprocess

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DATA = os.path.abspath(os.environ.get("DATA_DIR", os.path.join(_ROOT, "data")))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_TRACES = os.path.join(_DATA, "traces")
_CHECKPOINTS = os.path.join(_DATA, "checkpoints")
_WORKSPACES = os.path.join(_DATA, "workspaces")


def _dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _fmt(nbytes: int) -> str:
    v = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if v < 1024 or unit == "GB":
            return f"{v:.1f}{unit}"
        v /= 1024


def _live_session_ids():
    """Set of session ids currently in the DB, or None if the DB can't be read
    (in which case ORPHAN pruning is skipped entirely — never guess and delete)."""
    try:
        from server import db
        # list_sessions() returns dicts ({"id": ...}); tolerate objects too.
        return {(s["id"] if isinstance(s, dict) else s.id) for s in db.list_sessions()}
    except Exception as e:
        print(f"  (could not read sessions — skipping orphan pruning: {type(e).__name__}: {e})")
        return None


def _older_than(path: str, cutoff: float) -> bool:
    try:
        return os.path.getmtime(path) < cutoff
    except OSError:
        return False


def _chmod_retry(func, path, _exc):
    """shutil.rmtree onerror hook: Windows marks git's internal object files READ-ONLY, which
    blocks deletion — so old checkpoints that contain a cloned repo could never be reclaimed
    (WinError 5). Clear the read-only bit and retry the delete."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _rm(path: str, dry_run: bool) -> int:
    """Remove a file or tree; return the bytes it occupied (measured before removal)."""
    size = _dir_size(path) if os.path.isdir(path) else (os.path.getsize(path) if os.path.exists(path) else 0)
    if not dry_run:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, onerror=_chmod_retry)
            else:
                os.remove(path)
        except OSError as e:
            print(f"  ! could not remove {path}: {e}")
            return 0
    return size


def prune_traces(live_ids, days, dry_run, log=print):
    if not os.path.isdir(_TRACES):
        return 0, 0
    cutoff = time.time() - days * 86400
    freed = count = 0
    for name in os.listdir(_TRACES):
        if not name.endswith(".jsonl"):
            continue
        sid = name[:-len(".jsonl")]
        path = os.path.join(_TRACES, name)
        orphan = live_ids is not None and sid not in live_ids
        if orphan or _older_than(path, cutoff):
            freed += _rm(path, dry_run)
            count += 1
    if count:
        log(f"  traces:      {count} file(s), {_fmt(freed)} ({'would free' if dry_run else 'freed'})")
    return count, freed


def prune_checkpoints(live_ids, days, dry_run, log=print):
    if not os.path.isdir(_CHECKPOINTS):
        return 0, 0
    cutoff = time.time() - days * 86400
    freed = count = 0
    for sid in os.listdir(_CHECKPOINTS):
        sdir = os.path.join(_CHECKPOINTS, sid)
        if not os.path.isdir(sdir):
            continue
        # Orphaned session -> drop the whole checkpoint tree. Otherwise age out
        # individual checkpoints (the per-session count cap already bounds live ones).
        if live_ids is not None and sid not in live_ids:
            freed += _rm(sdir, dry_run)
            count += 1
            continue
        for cp in os.listdir(sdir):
            cpath = os.path.join(sdir, cp)
            if os.path.isdir(cpath) and _older_than(cpath, cutoff):
                freed += _rm(cpath, dry_run)
                count += 1
    if count:
        log(f"  checkpoints: {count} item(s), {_fmt(freed)} ({'would free' if dry_run else 'freed'})")
    return count, freed


def prune_workspaces(live_ids, dry_run, log=print):
    """ORPHANED workspaces only (session deleted). Never age-prunes — a live session's
    workspace is user data. project_* workspaces are shared and always kept."""
    if not os.path.isdir(_WORKSPACES) or live_ids is None:
        return 0, 0
    freed = count = 0
    for name in os.listdir(_WORKSPACES):
        wdir = os.path.join(_WORKSPACES, name)
        if not os.path.isdir(wdir) or name.startswith("project_") or name.startswith("_"):
            continue                       # keep project + internal (_bench_ws/_smoke) dirs
        if name not in live_ids:
            freed += _rm(wdir, dry_run)
            count += 1
    if count:
        log(f"  workspaces:  {count} orphaned dir(s), {_fmt(freed)} ({'would free' if dry_run else 'freed'})")
    return count, freed


def docker_image_prune(dry_run, log=print):
    if dry_run:
        log("  docker:      (dry-run) would run `docker image prune -f`")
        return
    try:
        out = subprocess.run(["docker", "image", "prune", "-f"],
                             capture_output=True, text=True, timeout=60)
        tail = (out.stdout or out.stderr or "").strip().splitlines()
        log("  docker:      " + (tail[-1] if tail else "pruned dangling images"))
    except FileNotFoundError:
        log("  docker:      (docker not found — skipped)")
    except Exception as e:
        log(f"  docker:      (skipped: {type(e).__name__}: {e})")


def sweep(days=30, workspaces=False, docker=False, dry_run=False, log=print):
    """Run the janitor. Returns (items_removed, bytes_freed). The server calls this at
    startup with the safe defaults (no workspaces, no docker)."""
    live = _live_session_ids()
    log(f"disk janitor: data={_DATA}  age>{days}d  "
        f"orphans={'on' if live is not None else 'skipped'}"
        f"{'  [DRY RUN]' if dry_run else ''}")
    items = freed = 0
    for fn in (lambda: prune_traces(live, days, dry_run, log),
               lambda: prune_checkpoints(live, days, dry_run, log)):
        c, b = fn()
        items += c
        freed += b
    if workspaces:
        c, b = prune_workspaces(live, dry_run, log)
        items += c
        freed += b
    if docker:
        docker_image_prune(dry_run, log)
    if items:
        log(f"disk janitor: {items} item(s), {_fmt(freed)} total "
            f"{'would be freed' if dry_run else 'freed'}.")
    else:
        log("disk janitor: nothing to reclaim.")
    return items, freed


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Reclaim disk from traces/checkpoints/workspaces.")
    ap.add_argument("--days", type=int, default=int(os.environ.get("MAX_TRACE_AGE_DAYS", "30")),
                    help="age threshold for traces/checkpoints (default 30)")
    ap.add_argument("--workspaces", action="store_true", help="also remove orphaned session workspaces")
    ap.add_argument("--docker", action="store_true", help="also `docker image prune -f`")
    ap.add_argument("--all", action="store_true", help="workspaces + docker + traces/checkpoints")
    ap.add_argument("--dry-run", action="store_true", help="show what would be freed; delete nothing")
    a = ap.parse_args(argv)
    sweep(days=a.days, workspaces=a.workspaces or a.all,
          docker=a.docker or a.all, dry_run=a.dry_run)


if __name__ == "__main__":
    _main()
