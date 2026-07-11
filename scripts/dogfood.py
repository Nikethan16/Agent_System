"""
dogfood.py — end-to-end self-engineering test you run locally.

Point the platform at a project, give it a task ("add a feature + a test", "write
tests and make them pass", …), and check the read → edit → run loop actually changed
the code and the tests are green. This is the proof you can aim it at a real codebase.

Usage (from the repo root, with your .env in place):
    python -m scripts.dogfood                     # built-in calc demo: add multiply() + test
    python -m scripts.dogfood --seed-only         # just seed + verify, no model calls
    python -m scripts.dogfood --dir path\to\proj  # use YOUR project (copied; non-destructive)
    python -m scripts.dogfood --dir . --in-place  # operate on the project in place (careful)
    python -m scripts.dogfood --task "Write pytest tests for utils.py and make them pass"
    python -m scripts.dogfood --force             # skip the model-availability pre-check

Windows tip: use the venv python explicitly, or the wrapper:
    .\.venv\Scripts\python.exe -m scripts.dogfood
    .\run_dogfood.ps1 -Dir .\myproj -Task "add a /health endpoint + a test"

Needs at least one working model key in .env (DEEPSEEK/DEEPINFRA/GEMINI/NVIDIA_NIM). For
the agent to run tests in-loop set AGENT_BASH_DOCKER_IMAGE; without it the harness runs
pytest on the result directly so you still get a pass/fail.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()                    # so keys in .env are visible when run directly
except Exception:
    pass

from core import tools                       # noqa: E402
from core.llm import Budget                  # noqa: E402

# ---- the built-in demo project ---------------------------------------------
SEED_FILES = {
    "calc.py": (
        '"""A tiny calculator library."""\n\n\n'
        "def add(a, b):\n    return a + b\n\n\n"
        "def subtract(a, b):\n    return a - b\n"
    ),
    "test_calc.py": (
        "import calc\n\n\n"
        "def test_add():\n    assert calc.add(2, 3) == 5\n\n\n"
        "def test_subtract():\n    assert calc.subtract(5, 2) == 3\n"
    ),
    "README.md": (
        "# calc\n\nA tiny calculator. Functions live in `calc.py`, tests in "
        "`test_calc.py`.\nRun `python -m pytest`.\n"
    ),
}

DEMO_TASK = (
    "This workspace contains a small Python project (calc.py + test_calc.py). "
    "Add a `multiply(a, b)` function to calc.py that returns a * b, add a matching "
    "test to test_calc.py, then run the test suite and make sure everything passes. "
    "Read the existing files first and match their style."
)
DEMO_ACCEPTANCE = "calc.py defines multiply(a, b); test_calc.py tests it; `python -m pytest` passes."

GENERIC_ACCEPTANCE = ("The requested change is implemented and `python -m pytest` passes "
                      "in the workspace. Do not weaken or delete tests to make them pass.")

_SKIP = {".git", ".venv", "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache"}


def seed_project(ws: str) -> None:
    os.makedirs(ws, exist_ok=True)
    for name, content in SEED_FILES.items():
        with open(os.path.join(ws, name), "w", encoding="utf-8") as f:
            f.write(content)


def verify_seed(ws: str) -> bool:
    ok = all(os.path.isfile(os.path.join(ws, n)) for n in SEED_FILES)
    print(f"  seed files present: {ok}")
    return ok


def copy_project(src: str, dst: str) -> None:
    """Copy a user project into a scratch workspace (skipping VCS/venv/build dirs)."""
    def ignore(_dir, names):
        return [n for n in names if n in _SKIP]
    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)


def _model_available() -> bool:
    """Probe the SAME fallback chains the run uses (coding + classify), so one dead
    model (e.g. a NIM floor id returning 410 Gone) doesn't cause a false 'no access'."""
    from core import llm
    from core.registry import registry
    probes = [("coding", registry.model_chain("tier2", task_type="coding")),
              ("classify", registry.model_chain("tier1", task_type="classify"))]
    ok = False
    for name, chain in probes:
        try:
            llm.complete_chain(chain, [{"role": "user", "content": "ok"}],
                               budget=Budget(max_usd=0.05), max_tokens=5)
            print(f"  {name} chain OK  -> {(chain or ['?'])[0]}")
            ok = True
        except Exception as e:
            print(f"  {name} chain FAILED: {type(e).__name__}: {str(e)[:140]}")
    if not ok:
        print("  Every chain failed. Likely a missing key (classify leads with Gemini) or "
              "stale model ids — run `python -m scripts.verify_models` to see which ids "
              "resolve, then update config/models.yaml (or the UI routing editor).")
    return ok


def _snapshot(ws: str) -> dict:
    """path -> (size, mtime) for every file, so we can show what the agent changed."""
    snap = {}
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in _SKIP]
        for fn in files:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, ws).replace("\\", "/")
            try:
                st = os.stat(p)
                snap[rel] = (st.st_size, st.st_mtime)
            except OSError:
                pass
    return snap


def _report_changes(before: dict, after: dict) -> None:
    new = [p for p in after if p not in before]
    changed = [p for p in after if p in before and after[p] != before[p]]
    if new:
        print("  new files:     " + ", ".join(sorted(new)[:12]))
    if changed:
        print("  changed files: " + ", ".join(sorted(changed)[:12]))
    if not new and not changed:
        print("  (no files changed — the agent didn't edit anything)")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _run_pytest(ws: str) -> bool:
    """True if `pytest` passes in the workspace (or there are no tests to run)."""
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ws,
                           capture_output=True, text=True, timeout=300)
        tail = (r.stdout or r.stderr or "").strip().splitlines()[-1:] or [""]
        print(f"  pytest: {tail[0]}")
        return r.returncode in (0, 5)      # 5 = "no tests collected" (nothing to fail)
    except Exception as e:
        print(f"  (could not run pytest: {e})")
        return False


def check_result(ws: str) -> bool:
    """Demo check: multiply() + a test were added and the suite passes."""
    calc = _read(os.path.join(ws, "calc.py"))
    test = _read(os.path.join(ws, "test_calc.py"))
    has_fn = "def multiply" in calc
    has_test = "multiply" in test
    print(f"  multiply() added to calc.py: {has_fn}")
    print(f"  test references multiply:    {has_test}")
    passed = _run_pytest(ws)
    return has_fn and has_test and passed


def run(args) -> int:
    scratch = tempfile.mkdtemp(prefix="dogfood_")
    demo = not args.dir

    if args.in_place and args.dir:
        ws = os.path.abspath(args.dir)
        print(f"workspace (IN PLACE): {ws}")
    elif args.dir:
        ws = os.path.join(scratch, "proj")
        copy_project(os.path.abspath(args.dir), ws)
        print(f"workspace (copy of {args.dir}): {ws}")
    else:
        ws = scratch
        seed_project(ws)
        print(f"workspace (built-in demo): {ws}")
        if not verify_seed(ws):
            print("FAIL: seeding failed.")
            return 1

    task = args.task or (DEMO_TASK if demo else None)
    if not task:
        print("ERROR: --dir needs a --task (what should the platform do to your project?).")
        return 2
    acceptance = DEMO_ACCEPTANCE if (demo and not args.task) else GENERIC_ACCEPTANCE

    if args.seed_only:
        print("PASS: seed-only (project prepared + verified). Drop --seed-only to run the "
              "full read→edit→run loop.")
        return 0

    if not args.force and not _model_available():
        print("SKIP: no usable model — see guidance above (verify_models / keys). "
              "Use --force to run anyway.")
        return 2

    from core.orchestrator import handle_task
    budget = Budget(max_usd=args.max_usd, max_iterations=args.max_iter)
    before = _snapshot(ws)
    print(f"\n>> task: {task}\n")
    with tools.using_workspace(ws):
        final = handle_task(task, budget=budget, review="auto", acceptance=acceptance)
    print(f"\nagent said: {(final or '')[:400]}\n")
    print(f"spent ${budget.spent_usd:.4f} over {budget.iterations} iterations")
    _report_changes(before, _snapshot(ws))

    ok = check_result(ws) if demo else _run_pytest(ws)
    print("\n" + ("PASS ✅  the platform made the change and the tests are green."
                  if ok else "FAIL ❌  see the checks above."))
    print(f"(workspace kept at: {ws})")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="End-to-end self-engineering test.")
    ap.add_argument("--dir", help="a local project to use (default: built-in calc demo)")
    ap.add_argument("--task", help="what to ask the platform to do")
    ap.add_argument("--in-place", action="store_true", help="edit --dir directly (not a copy)")
    ap.add_argument("--seed-only", action="store_true", help="prepare + verify only, no model calls")
    ap.add_argument("--force", action="store_true", help="skip the model-availability pre-check")
    ap.add_argument("--max-usd", type=float, default=1.0, help="budget cap for the run (USD)")
    ap.add_argument("--max-iter", type=int, default=24, help="iteration cap for the run")
    sys.exit(run(ap.parse_args()))
