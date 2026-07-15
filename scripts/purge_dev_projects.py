"""
purge_dev_projects.py — remove clutter test PROJECTS (and everything under them)
from a LOCAL dev database.

Repeated local test runs seed throwaway projects (budget-test, capped, only-this,
overview-proj, status, uncapped) that pile up in the sidebar. This deletes them and
cascades to their sessions + all per-session rows (messages, events, checkpoints,
runstate, approvals, memory, jobs, schedules) and the projects' spend rows, then
best-effort removes their workspace folders on disk.

LOCAL DEV ONLY. It is deliberately name-scoped and refuses to touch production data
(the VM never runs this). Stdlib-only (sqlite3) so it needs no app deps.

Usage:
    python -m scripts.purge_dev_projects --dry-run          # show what would go
    python -m scripts.purge_dev_projects --yes              # actually delete
    python -m scripts.purge_dev_projects --names foo,bar --yes
    python -m scripts.purge_dev_projects --db data/app.db --yes
"""
import argparse
import os
import shutil
import sqlite3
import sys

DEFAULT_NAMES = ["only-this", "capped", "budget-test", "overview-proj", "status", "uncapped"]

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_db() -> str:
    return os.environ.get("APP_DB", os.path.join(_ROOT, "data", "app.db"))


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


def purge(db_path: str, names, dry_run: bool = True) -> dict:
    if not os.path.isfile(db_path):
        raise SystemExit(f"no database at {db_path}")
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys=OFF")
    cur = con.cursor()

    pids = [r[0] for r in cur.execute(
        f"SELECT id FROM project WHERE name IN ({_placeholders(len(names))})", names)]
    sids = []
    if pids:
        sids = [r[0] for r in cur.execute(
            f"SELECT id FROM session WHERE project_id IN ({_placeholders(len(pids))})", pids)]

    # tables keyed by session_id (only those that exist in this schema)
    existing = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    per_session = [t for t in
                   ("message", "event", "checkpoint", "runstate", "approval",
                    "memory", "job", "schedule") if t in existing]

    counts = {"projects": len(pids), "sessions": len(sids)}
    for t in per_session:
        if sids:
            counts[t] = cur.execute(
                f"SELECT COUNT(*) FROM {t} WHERE session_id IN ({_placeholders(len(sids))})",
                sids).fetchone()[0]
        else:
            counts[t] = 0
    counts["spend"] = cur.execute(
        f"SELECT COUNT(*) FROM spend WHERE project_id IN ({_placeholders(len(pids))})",
        pids).fetchone()[0] if pids else 0

    if dry_run or not pids:
        con.close()
        return counts

    # ---- delete (children first) ----
    if sids:
        sq = _placeholders(len(sids))
        for t in per_session:
            cur.execute(f"DELETE FROM {t} WHERE session_id IN ({sq})", sids)
        cur.execute(f"DELETE FROM session WHERE id IN ({sq})", sids)
    pq = _placeholders(len(pids))
    cur.execute(f"DELETE FROM spend WHERE project_id IN ({pq})", pids)
    cur.execute(f"DELETE FROM project WHERE id IN ({pq})", pids)
    con.commit()
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    con.close()

    # ---- best-effort filesystem cleanup (never fatal) ----
    for pid in pids:
        shutil.rmtree(os.path.join(_ROOT, "data", "projects", pid), ignore_errors=True)
    for sid in sids:
        shutil.rmtree(os.path.join(_ROOT, "data", "workspaces", sid), ignore_errors=True)
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description="Purge clutter dev projects from a local DB.")
    ap.add_argument("--db", default=_default_db(), help="path to app.db (default: data/app.db or $APP_DB)")
    ap.add_argument("--names", default=",".join(DEFAULT_NAMES),
                    help="comma-separated project names to delete")
    ap.add_argument("--dry-run", action="store_true", help="show what would be deleted, change nothing")
    ap.add_argument("--yes", action="store_true", help="actually delete (required unless --dry-run)")
    args = ap.parse_args(argv)

    names = [n.strip() for n in args.names.split(",") if n.strip()]
    dry = args.dry_run or not args.yes
    counts = purge(args.db, names, dry_run=dry)

    label = "WOULD DELETE" if dry else "DELETED"
    print(f"{label} from {args.db} (names: {', '.join(names)}):")
    for k in ["projects", "sessions", "message", "event", "checkpoint", "runstate",
              "approval", "memory", "job", "schedule", "spend"]:
        if k in counts:
            print(f"  {k:<11} {counts[k]}")
    if dry:
        print("\n(dry run — re-run with --yes to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
