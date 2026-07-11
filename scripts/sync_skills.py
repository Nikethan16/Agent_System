#!/usr/bin/env python
"""
sync_skills.py — CLI for the Skills Hub.

    python -m scripts.sync_skills list                     # allowlisted sources
    python -m scripts.sync_skills available <source>       # skills a source offers
    python -m scripts.sync_skills sync <source> <skill>    # fetch one (lands DISABLED)
    python -m scripts.sync_skills status                   # local skills + enabled state
    python -m scripts.sync_skills enable <skill>           # enable after review
    python -m scripts.sync_skills disable <skill>

Synced skills arrive DISABLED — review the SKILL.md, then `enable` it before it can
influence any task. Only sources in config/skill_sources.yaml can be fetched.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core import skills as skill_lib
from core import skill_sync


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]

    if cmd == "list":
        for s in skill_sync._sources():
            print(f"  {s['name']:<20} {s['repo']}  (branch {s.get('branch','main')})")
        return 0

    if cmd == "available" and rest:
        for a in skill_sync.list_available(rest[0]):
            mark = "synced" if a["synced"] else "     "
            print(f"  [{mark}] {a['name']:<30} {a['source']}")
        return 0

    if cmd == "sync" and len(rest) >= 2:
        r = skill_sync.sync_skill(rest[0], rest[1])
        print(f"  synced {r['name']} ({r['files']} files) — DISABLED; review then enable.")
        return 0

    if cmd == "status":
        for s in skill_lib.all_catalog():
            mark = "on " if s["enabled"] else "off"
            src = s["source"] or "bundled"
            print(f"  [{mark}] {s['name']:<30} {src}")
        return 0

    if cmd in ("enable", "disable") and rest:
        new = skill_lib.set_enabled(rest[0], cmd == "enable")
        print(f"  {rest[0]}: {'enabled' if new else 'disabled'}")
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
