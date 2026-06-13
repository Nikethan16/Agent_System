"""
backup.py — back up everything stateful into one timestamped zip.

What's inside data/ is the only thing you can't rebuild from the repo: the SQLite DB
(chats, messages, memory, jobs, projects, spend), per-session workspaces, checkpoints,
and traces. This zips all of it so a daily backup is one command.

    python scripts/backup.py                 # -> backups/agentcore-<UTC timestamp>.zip
    python scripts/backup.py --out /path/dir # choose where the zip lands
    python scripts/backup.py --keep 10       # prune to the newest N backups

OFF-SITE (recommended once hosted): set BACKUP_UPLOAD_CMD to a command that pushes the
zip somewhere durable; "{zip}" is replaced with the archive path. Examples:
    BACKUP_UPLOAD_CMD="rclone copy {zip} gdrive:agentcore-backups"
    BACKUP_UPLOAD_CMD="aws s3 cp {zip} s3://my-bucket/agentcore/"
Then schedule it with OS cron / Windows Task Scheduler, e.g. daily:
    python scripts/backup.py --keep 14

Restore = stop the app, unzip the archive over the project root, restart.
"""
import os
import sys
import zipfile
import argparse
import subprocess
from datetime import datetime, timezone

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DATA = os.path.abspath(os.environ.get("DATA_DIR", os.path.join(_ROOT, "data")))


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def make_backup(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, f"agentcore-{_ts()}.zip")
    if not os.path.isdir(_DATA):
        print(f"nothing to back up: {_DATA} does not exist")
        return ""
    count = 0
    # SQLite WAL note: copying the .db plus its -wal/-shm is fine for a cold/at-rest
    # backup; for a guaranteed-consistent snapshot, stop the app first.
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirs, names in os.walk(_DATA):
            # skip our own backup output and any temp test dirs
            dirs[:] = [d for d in dirs if not d.startswith("_")]
            for n in names:
                full = os.path.join(dirpath, n)
                arc = os.path.relpath(full, _ROOT)
                try:
                    z.write(full, arc)
                    count += 1
                except OSError as e:
                    print(f"  skip {arc}: {e}")
    size = os.path.getsize(dest)
    print(f"backed up {count} files -> {dest} ({size/1_048_576:.2f} MB)")
    return dest


def prune(out_dir: str, keep: int):
    zips = sorted(
        (os.path.join(out_dir, f) for f in os.listdir(out_dir)
         if f.startswith("agentcore-") and f.endswith(".zip")),
        reverse=True,
    )
    for old in zips[keep:]:
        os.remove(old)
        print(f"pruned old backup {os.path.basename(old)}")


def upload(dest: str):
    """Push the archive off-site via $BACKUP_UPLOAD_CMD ({zip} -> the archive path).
    No-op unless the env var is set, so local-only backups need nothing."""
    cmd = os.environ.get("BACKUP_UPLOAD_CMD", "").strip()
    if not cmd or not dest:
        return
    full = cmd.replace("{zip}", dest)
    print(f"uploading off-site: {full}")
    try:
        r = subprocess.run(full, shell=True, capture_output=True, text=True, timeout=600)
        print(f"  upload exit={r.returncode}" + (f" — {r.stderr[:200]}" if r.returncode else ""))
    except Exception as e:
        print(f"  upload failed: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(_ROOT, "backups"))
    ap.add_argument("--keep", type=int, default=0, help="keep only the newest N backups (0 = keep all)")
    args = ap.parse_args()
    dest = make_backup(args.out)
    if dest:
        upload(dest)   # off-site copy if BACKUP_UPLOAD_CMD is configured
    if args.keep > 0:
        prune(args.out, args.keep)
    return 0 if dest else 1


if __name__ == "__main__":
    sys.exit(main())
