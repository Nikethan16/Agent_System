#!/usr/bin/env python3
"""inspect_run.py — read-only diagnostic dump of one run: full event timeline,
span-tree summary (cost/tokens/duration per agent/tool), every file the run
generated in its workspace, and the last stored chat message.

Pure read — touches no orchestration code, just data/traces/*.jsonl, the
session workspace, and the sqlite DB. Use this to verify what a run actually
did, not just whether it finished.

Usage:
  python3 scripts/inspect_run.py --list [N]     # recent sessions: id, created, title
  python3 scripts/inspect_run.py <session_id>   # full dump for one session
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import db
from server.trace import load_trace, build_tree

TEXT_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json",
            ".md", ".txt", ".yaml", ".yml", ".sh"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv"}
MAX_FILE_LINES = 400

# Fields printed first, in this order, when present on an event.
_PRIORITY_KEYS = ("agent", "tool", "name", "model", "tier", "task_type", "reason",
                   "approved", "step", "subtask", "args", "text", "cost", "tokens",
                   "iterations", "pass")


def _trunc(v, n=200):
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s if len(s) <= n else s[:n] + f"...[{len(s)}ch]"


def list_sessions(n=20):
    sessions = sorted(db.list_sessions(), key=lambda s: s["created_at"], reverse=True)[:n]
    print(f"{'id':36} {'created_at':20} title")
    for s in sessions:
        print(f"{s['id']:36} {s['created_at']:20} {s['title']}")


def dump_timeline(session_id):
    events = load_trace(session_id)
    if not events:
        print(f"(no trace found for {session_id} — check the id)")
        return
    print(f"\n==== TIMELINE ({len(events)} events) ====")
    t0 = events[0].get("ts")
    for e in events:
        ts = e.get("ts")
        rel = f"+{ts - t0:6.1f}s" if ts and t0 else "?"
        typ = e.get("type", "?")
        extras = {k: v for k, v in e.items() if k not in ("ts", "type", "session_id")}
        parts = []
        for k in _PRIORITY_KEYS:
            if k in extras:
                parts.append(f"{k}={_trunc(extras.pop(k))}")
        for k, v in extras.items():
            parts.append(f"{k}={_trunc(v, 100)}")
        print(f"  [{rel}] {typ:16} " + " ".join(parts))


def dump_tree_summary(session_id):
    tree = build_tree(session_id)
    totals = tree["totals"]
    print("\n==== SUMMARY ====")
    print(f"  events: {tree['events_count']}  cost: ${totals['cost']:.4f}  "
          f"tokens: {totals['tokens']}  duration: {(totals['duration_ms'] or 0) / 1000:.1f}s")

    def walk(node, depth=0):
        dur = (node.get("duration_ms") or 0) / 1000
        model = f" model={node.get('model')}" if node.get("model") else ""
        print(f"  {'  ' * depth}- {node['name']} ({dur:.1f}s, ${node['cost']:.4f}, "
              f"{node['tokens']}tok){model}")
        for c in node["children"]:
            walk(c, depth + 1)
    walk(tree["root"])


def dump_workspace(session_id):
    ws = db.session_workspace(session_id)
    print(f"\n==== WORKSPACE FILES ({ws}) ====")
    found = False
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            found = True
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, ws)
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TEXT_EXT:
                print(f"\n--- {rel} (binary/unsupported, skipped) ---")
                continue
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except OSError as e:
                print(f"\n--- {rel} (unreadable: {e}) ---")
                continue
            print(f"\n--- {rel} ({len(lines)} lines) ---")
            print("".join(lines[:MAX_FILE_LINES]))
            if len(lines) > MAX_FILE_LINES:
                print(f"... [{len(lines) - MAX_FILE_LINES} more lines truncated]")
    if not found:
        print("  (empty — no files generated)")


def dump_final_answer(session_id):
    msgs = db.get_messages(session_id)
    if not msgs:
        return
    last = msgs[-1]
    print(f"\n==== LAST STORED MESSAGE (role={last['role']}) ====")
    print(_trunc(last["content"], 2000))


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    if sys.argv[1] == "--list":
        list_sessions(int(sys.argv[2]) if len(sys.argv) > 2 else 20)
        return
    session_id = sys.argv[1]
    print(f"session: {session_id}")
    s = db.get_session(session_id)
    if s:
        print(f"title:   {s['title']}")
    dump_timeline(session_id)
    dump_tree_summary(session_id)
    dump_workspace(session_id)
    dump_final_answer(session_id)


if __name__ == "__main__":
    main()
