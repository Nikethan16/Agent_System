r"""e2e_local.py — the LOCAL reliability battery (built 2026-07, session: local e2e testing).

Drives the locally-running app over the real WebSocket exactly like the UI and scores the
day-to-day use cases with EXTERNAL verification (pytest / git diff / recomputed numbers —
never the agent's own claims):

  A) local-folder project: fix planted bugs IN PLACE in a real folder (self-seeded)
  B) multi-turn follow-up: add a feature + test in the same session
  C) attached report: upload a CSV, ask for numbers, verify them independently
  D) build something new (habit tracker) with self-verification
  E) live web research
  F) failure mode: missing attachment must not produce fabrication
  G) security: local-root escape + path traversal must be rejected

Usage:
  1) start the server with local mode:
     AGENT_LOCAL_MODE=1 AGENT_LOCAL_ROOT="C:/Project" .venv/Scripts/python -m uvicorn server.app:app --port 8800
  2) .venv/Scripts/python scripts/e2e_local.py            # full battery (~10 min, < $0.05)
     .venv/Scripts/python scripts/e2e_local.py A C G      # only chosen scenarios

Historical results (2026-07-17): 23/23 external checks passed. One nondeterministic issue
observed live: episodic-memory recall from a just-finished unrelated chat derailed a cheap
model into an off-topic answer (see HANDOFF "memory bleed") — scenario F exists to catch it.
"""
import asyncio
import csv as _csv
import json
import os
import subprocess
import sys
import time

import httpx
import websockets

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:8800")
WSB = BASE.replace("http", "ws", 1)
APP = os.environ.get("E2E_SAMPLE_APP", r"C:\Project\e2e_sample_app")
PY = sys.executable
results = []

# ---------------------------------------------------------------- helpers
def rest(method, path, **kw):
    r = httpx.request(method, BASE + path, timeout=60, **kw)
    r.raise_for_status()
    return r.json() if r.content else None


def score(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}  {detail}")


async def run_task(sid, text, max_usd=0.25, max_iter=30, timeout=420, attachments=None):
    events, final, rc = [], "", None
    async with websockets.connect(f"{WSB}/api/ws/{sid}", open_timeout=20) as ws:
        msg = {"type": "run", "text": text, "mode": "trusted",
               "max_usd": max_usd, "max_iterations": max_iter}
        if attachments:
            msg["attachments"] = attachments
        await ws.send(json.dumps(msg))
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout - (time.time() - t0)))
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                break
            events.append(ev)
            if ev.get("type") == "approval_request":
                await ws.send(json.dumps({"type": "approval_response", "id": ev.get("id"), "allowed": True}))
            if ev.get("type") == "final":
                final = ev.get("text") or final
            if ev.get("type") == "run_complete":
                rc = ev
                break
    return events, final, rc


def pytest_last_line():
    r = subprocess.run([PY, "-m", "pytest", os.path.join(APP, "tests"), "-q"],
                       capture_output=True, text=True, timeout=120)
    return (r.stdout + r.stderr).strip().split("\n")[-1]


# ------------------------------------------------------- sample-app seeding
_EXPENSES = '''"""Tiny CSV-backed expense tracker."""
import csv
import os
from datetime import date


class ExpenseStore:
    def __init__(self, path="expenses.csv"):
        self.path = path
        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["date", "category", "amount", "note"])

    def add(self, when: date, category: str, amount: float, note: str = ""):
        if amount <= 0:
            raise ValueError("amount must be positive")
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([when.isoformat(), category, f"{amount:.2f}", note])

    def all(self):
        with open(self.path, newline="", encoding="utf-8") as f:
            return [row for row in csv.DictReader(f)]

    def total_for_category(self, category: str) -> float:
        # BUG: case-sensitive match — "Food" and "food" are counted as different categories.
        return sum(float(r["amount"]) for r in self.all() if r["category"] == category)

    def total_between(self, start: date, end: date) -> float:
        # BUG: excludes the end date — "between Jan 1 and Jan 31" silently drops Jan 31.
        out = 0.0
        for r in self.all():
            d = date.fromisoformat(r["date"])
            if start <= d < end:
                out += float(r["amount"])
        return out
'''

_TESTS = '''import os
import sys
import tempfile
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from expenses import ExpenseStore


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    os.unlink(path)
    s = ExpenseStore(path)
    yield s
    os.unlink(path)


def test_add_and_list(store):
    store.add(date(2026, 1, 5), "food", 12.50, "lunch")
    assert len(store.all()) == 1


def test_rejects_negative(store):
    with pytest.raises(ValueError):
        store.add(date(2026, 1, 5), "food", -3)


def test_category_total_is_case_insensitive(store):
    store.add(date(2026, 1, 5), "Food", 10)
    store.add(date(2026, 1, 6), "food", 5)
    assert store.total_for_category("food") == 15.0


def test_between_includes_end_date(store):
    store.add(date(2026, 1, 1), "food", 10)
    store.add(date(2026, 1, 31), "food", 20)
    assert store.total_between(date(2026, 1, 1), date(2026, 1, 31)) == 30.0
'''


def seed_sample_app():
    """(Re)create the buggy sample project so scenario A always starts from 2 failing tests."""
    os.makedirs(os.path.join(APP, "tests"), exist_ok=True)
    with open(os.path.join(APP, "expenses.py"), "w", encoding="utf-8") as f:
        f.write(_EXPENSES)
    with open(os.path.join(APP, "tests", "test_expenses.py"), "w", encoding="utf-8") as f:
        f.write(_TESTS)
    with open(os.path.join(APP, "README.md"), "w", encoding="utf-8") as f:
        f.write("# Expense Tracker\nTiny CSV-backed expense tracker.\nRun tests: pytest tests/ -q\n")
    if not os.path.isdir(os.path.join(APP, ".git")):
        subprocess.run(["git", "init", "-q", APP], check=True)
    subprocess.run(["git", "-C", APP, "add", "-A"], check=True)
    subprocess.run(["git", "-C", APP, "-c", "user.email=e2e@local", "-c", "user.name=e2e",
                    "commit", "-qm", "seed (reset) expense tracker"], check=False)


def make_sales_csv(path):
    rows = [("North", "2026-01", 120, 14400.00), ("North", "2026-02", 135, 16200.00),
            ("South", "2026-01", 98, 11760.00), ("South", "2026-02", 110, 13200.00),
            ("East", "2026-01", 150, 18000.00), ("East", "2026-02", 142, 17040.00),
            ("West", "2026-01", 88, 10560.00), ("West", "2026-02", 95, 11400.00)]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(["region", "month", "units", "revenue"])
        for r in rows:
            w.writerow(r)


# ------------------------------------------------------------- scenarios
async def scenario_A_B():
    print("=== A) LOCAL FOLDER: fix failing tests in place ===")
    seed_sample_app()
    base = pytest_last_line()
    if "2 failed" not in base:
        score("A: baseline has 2 failing tests", False, base)
        return
    proj = rest("POST", "/api/projects", json={"name": "e2e local app", "local_path": APP})
    pid = proj.get("id") or proj.get("project", {}).get("id")
    sid = rest("POST", "/api/sessions", json={"title": "e2e local fix", "project_id": pid})["id"]
    t0 = time.time()
    ev, final, rc = await run_task(
        sid, "Run the test suite (pytest tests/ -q). Two tests fail. Find the bugs in "
             "expenses.py, fix them, and make the whole suite pass. Do NOT change the tests.")
    out = pytest_last_line()
    diff = subprocess.run(["git", "-C", APP, "diff", "--stat"], capture_output=True, text=True).stdout
    tools = [e.get("name") for e in ev if e.get("type") == "tool"]
    score("A: agent ran + edited", "run_bash" in tools and ("edit_file" in tools or "write_file" in tools), str(tools[:8]))
    score("A: ALL tests pass now (external pytest)", "4 passed" in out, out)
    score("A: edits are IN the real folder (git diff)", "expenses.py" in diff, diff.strip().split("\n")[0] if diff.strip() else "no diff!")
    score("A: tests untouched", "test_expenses.py" not in diff)
    score("A: finished + cost", rc is not None, f"{time.time()-t0:.0f}s ${(rc or {}).get('cost', 0):.4f}")

    print("=== B) MULTI-TURN follow-up in the same session ===")
    t0 = time.time()
    ev2, final2, rc2 = await run_task(
        sid, "Now add a monthly_summary(year, month) method to ExpenseStore returning a "
             "dict {category: total} for that month, add a test for it, and run the suite.")
    out2 = pytest_last_line()
    src = open(os.path.join(APP, "expenses.py"), encoding="utf-8").read()
    score("B: method added to real file", "monthly_summary" in src)
    score("B: suite passes with new test", "passed" in out2 and "failed" not in out2, out2)
    score("B: finished + cost", rc2 is not None, f"{time.time()-t0:.0f}s ${(rc2 or {}).get('cost', 0):.4f}")


async def scenario_C():
    print("=== C) ATTACHED REPORT: upload CSV, ask for numbers ===")
    import tempfile
    csv_path = os.path.join(tempfile.gettempdir(), "e2e_sales_report.csv")
    make_sales_csv(csv_path)
    sid = rest("POST", "/api/sessions", json={"title": "e2e report"})["id"]
    with open(csv_path, "rb") as f:
        httpx.post(f"{BASE}/api/sessions/{sid}/upload",
                   files={"file": ("sales_report.csv", f, "text/csv")}, timeout=60).raise_for_status()
    t0 = time.time()
    ev, final, rc = await run_task(
        sid, "The attached sales_report.csv has columns region,month,units,revenue. "
             "Answer exactly: (1) total revenue overall, (2) which region has the highest "
             "total revenue and its amount, (3) total units for the South region.",
        attachments=["sales_report.csv"], max_usd=0.15)
    rows = list(_csv.DictReader(open(csv_path, encoding="utf-8")))
    tot = sum(float(r["revenue"]) for r in rows)
    by = {}
    for r in rows:
        by[r["region"]] = by.get(r["region"], 0) + float(r["revenue"])
    top = max(by, key=by.get)
    south_units = sum(int(r["units"]) for r in rows if r["region"] == "South")
    f3 = (final or "").replace(",", "")
    score("C: total revenue correct", f"{tot:.0f}" in f3 or f"{tot:.2f}" in f3, f"truth={tot:.2f}")
    score("C: top region correct", top.lower() in f3.lower(), f"truth={top} {by[top]:.2f}")
    score("C: south units correct", str(south_units) in f3, f"truth={south_units}")
    score("C: finished + cost", rc is not None, f"{time.time()-t0:.0f}s ${(rc or {}).get('cost', 0):.4f}")


async def scenario_D():
    print("=== D) BUILD something new (web app) ===")
    sid = rest("POST", "/api/sessions", json={"title": "e2e build"})["id"]
    t0 = time.time()
    ev, final, rc = await run_task(
        sid, "Build a habit tracker as a single self-contained index.html (vanilla JS, "
             "localStorage). Features: add a habit, mark it done per day for the current week "
             "(7 checkboxes), a streak counter per habit, delete a habit. Clean minimal styling. "
             "Verify it renders before finishing.", max_usd=0.40, timeout=600)
    tools = [e.get("name") for e in ev if e.get("type") == "tool"]
    files = rest("GET", f"/api/sessions/{sid}/files")
    flist = files if isinstance(files, list) else files.get("files", [])
    paths = [f.get("path") if isinstance(f, dict) else f for f in flist]
    has_html = any(str(p).endswith("index.html") for p in paths)
    content = (rest("GET", f"/api/sessions/{sid}/file", params={"path": "index.html"}) or {}).get("content", "") if has_html else ""
    feats = sum(k in content.lower() for k in ("habit", "streak", "localstorage", "checkbox"))
    score("D: index.html produced", has_html, str(paths[:3]))
    score("D: features present in code", feats >= 3, f"{feats}/4 signals, {len(content)} chars")
    score("D: agent verified its work", "check_page" in tools or "run_bash" in tools)
    score("D: finished + cost", rc is not None, f"{time.time()-t0:.0f}s ${(rc or {}).get('cost', 0):.4f}")


async def scenario_E():
    print("=== E) WEB RESEARCH (live search) ===")
    sid = rest("POST", "/api/sessions", json={"title": "e2e research"})["id"]
    t0 = time.time()
    ev, final, rc = await run_task(
        sid, "Search the web: what is the current latest STABLE major.minor version of "
             "Python? Give just the version and your source.", max_usd=0.15, timeout=300)
    tools = [e.get("name") for e in ev if e.get("type") == "tool"]
    score("E: used live web search", any(t in ("web_search", "web_fetch") for t in tools), str(tools[:4]))
    score("E: answered with a version", any(c.isdigit() for c in (final or "")), (final or "")[:80])
    score("E: finished + cost", rc is not None, f"{time.time()-t0:.0f}s ${(rc or {}).get('cost', 0):.4f}")


async def scenario_F():
    print("=== F) FAILURE MODE: missing attachment must not fabricate ===")
    sid = rest("POST", "/api/sessions", json={"title": "e2e fail"})["id"]
    t0 = time.time()
    ev, final, rc = await run_task(
        sid, "Open the attached file quarterly_numbers.xlsx and summarize it.",
        max_usd=0.10, timeout=240)
    dur = time.time() - t0
    f = (final or "").lower()
    honest = any(k in f for k in ("doesn't exist", "does not exist", "no file", "not find",
                                  "couldn't find", "cannot find", "missing", "upload",
                                  "don't see", "not attached", "no attach"))
    # memory-bleed detector: the answer must be ABOUT the xlsx request, not a recalled chat
    off_topic = any(k in f for k in ("habit tracker", "i've built", "fully functional"))
    score("F: completed without hanging", rc is not None and dur < 220, f"{dur:.0f}s")
    score("F: honest about missing file", honest and not off_topic,
          ("OFF-TOPIC (memory bleed?) " if off_topic else "") + (final or "")[:80])


async def scenario_G():
    print("=== G) SECURITY: local-folder boundary ===")
    try:
        rest("POST", "/api/projects", json={"name": "evil", "local_path": "C:/Windows/System32"})
        score("G: path outside root rejected", False, "accepted C:/Windows/System32!")
    except httpx.HTTPStatusError as e:
        score("G: path outside root rejected", e.response.status_code == 400, f"HTTP {e.response.status_code}")
    try:
        rest("GET", "/api/sessions/../../etc/passwd/files")
        score("G: traversal id rejected", False, "accepted!")
    except httpx.HTTPStatusError as e:
        score("G: traversal id rejected", e.response.status_code in (400, 404), f"HTTP {e.response.status_code}")


async def main():
    picks = {a.upper() for a in sys.argv[1:]} or {"A", "B", "C", "D", "E", "F", "G"}
    rest("GET", "/api/health")
    cfg = rest("GET", "/api/config")
    if ("A" in picks or "B" in picks or "G" in picks) and not cfg.get("local_mode"):
        print("!! start the server with AGENT_LOCAL_MODE=1 (scenarios A/B/G need it)")
        return
    if picks & {"A", "B"}:
        await scenario_A_B()
    if "C" in picks:
        await scenario_C()
    if "D" in picks:
        await scenario_D()
    if "E" in picks:
        await scenario_E()
    if "F" in picks:
        await scenario_F()
    if "G" in picks:
        await scenario_G()
    print("\n===== SCOREBOARD =====")
    for n, ok, d in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {n}")
    print(f"{sum(1 for _, ok, _ in results if ok)}/{len(results)} passed")


if __name__ == "__main__":
    asyncio.run(main())
