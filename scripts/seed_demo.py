"""Seed the DB with representative sessions + files for visual QA of the UI.
Run once against a scratch AGENT_DATA_DIR, then start the server against the same dir.
Not shipped behaviour — a dev/QA aid."""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import db  # noqa: E402

db.init_db()


def _set_time(session_id, dt, starred=False):
    from sqlmodel import Session as DBSession
    with DBSession(db.engine) as s:
        obj = s.get(db.Session, session_id)
        obj.updated_at = dt.isoformat()
        obj.created_at = dt.isoformat()
        obj.starred = starred
        s.add(obj)
        s.commit()


now = datetime.now(timezone.utc)
SEED = [
    ("Weather + cycle rental at Narsingi", now - timedelta(minutes=4), False),
    ("Realized-vol cone + cost gate", now - timedelta(hours=1), False),
    ("Deploy to Oracle VM — systemd", now - timedelta(hours=3), True),
    ("Refactor the orchestration layer", now - timedelta(days=1, hours=2), False),
    ("Skills Hub security scan review", now - timedelta(days=1, hours=6), False),
    ("Telegram 1717895615", now - timedelta(days=3), False),
    ("Corporate filings calendar", now - timedelta(days=5), False),
    ("ANN index benchmark notes", now - timedelta(days=20), False),
]

first_id = None
for title, dt, starred in SEED:
    sess = db.create_session(title=title)
    db.add_message(sess.id, "user", f"({title})")
    db.rename_session(sess.id, title)   # keep the intended title (add_message auto-title would match anyway)
    _set_time(sess.id, dt, starred)
    if first_id is None:
        first_id = sess.id

# Give the top chat some workspace files so the right panel shows real content.
ws = db.session_workspace(first_id)
os.makedirs(ws, exist_ok=True)
FILES = {
    "PLAN.md": "# Plan\n\n1. Look up weather\n2. Find rental shops\n3. Synthesise\n",
    "findings.md": "# Findings\n\n- Partly cloudy, ~35C\n- Smart Bike Park, Dr.Cycles\n- Rs.50/hr regular, Rs.80/hr gear\n",
    "database.py": '"""Database setup and SQLAlchemy models."""\nfrom sqlalchemy import Column, String\n\n\ndef make_engine(url):\n    return create_engine(url)\n',
    "main.py": "from database import make_engine\n\n\ndef run():\n    return make_engine('sqlite:///./app.db')\n",
    "acceptance_criteria.md": "# Acceptance\n\n- Prints rates\n- Lists two shops\n",
}
for name, content in FILES.items():
    with open(os.path.join(ws, name), "w", encoding="utf-8") as f:
        f.write(content)

print(f"Seeded {len(SEED)} sessions; top chat {first_id} has {len(FILES)} files.")
print(f"DATA_DIR = {db.DATA_DIR}")
