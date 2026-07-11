"""
dogfood.py — end-to-end self-engineering test.

Seeds a small, real multi-file Python project into a scratch workspace, then asks the
platform to "add a feature + a test, and run it" and checks that the read → edit → run
loop actually changed the code and the tests pass. This is the proof that you can point
the platform at an existing codebase and get a working feature back.

Usage:
    python -m scripts.dogfood --seed-only     # just seed + verify seeding (no model calls)
    python -m scripts.dogfood                 # full run — NEEDS model keys (+ Docker for the
                                              # in-agent test run); falls back to a host pytest
                                              # check of the result if the sandbox is absent.

Env needed for the full run: at least one working model key (e.g. GEMINI_API_KEY /
NVIDIA_NIM_API_KEY / DEEPSEEK_API_KEY). For the agent to run the tests itself, set
AGENT_BASH_DOCKER_IMAGE; without it the harness still verifies the edit and runs pytest
on the result directly.
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import tools                       # noqa: E402
from core.llm import Budget                  # noqa: E402

# ---- the seed project -------------------------------------------------------
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

TASK = (
    "This workspace contains a small Python project (calc.py + test_calc.py). "
    "Add a `multiply(a, b)` function to calc.py that returns a * b, add a matching "
    "test to test_calc.py, then run the test suite and make sure everything passes. "
    "Read the existing files first and match their style."
)
ACCEPTANCE = "calc.py defines multiply(a, b); test_calc.py tests it; `python -m pytest` passes."


def seed_project(ws: str) -> None:
    os.makedirs(ws, exist_ok=True)
    for name, content in SEED_FILES.items():
        with open(os.path.join(ws, name), "w", encoding="utf-8") as f:
            f.write(content)


def verify_seed(ws: str) -> bool:
    ok = all(os.path.isfile(os.path.join(ws, n)) for n in SEED_FILES)
    print(f"  seed files present: {ok}")
    return ok


def _model_available() -> bool:
    """Cheap probe: resolve a cheap model and make one tiny call. False when no
    key/network so the harness can SKIP cleanly instead of erroring."""
    try:
        from core import llm
        from core.registry import registry
        model = registry.model_for_tier("tier1")
        llm.complete(model, [{"role": "user", "content": "ok"}],
                     budget=Budget(max_usd=0.02), max_tokens=5)
        return True
    except Exception as e:
        print(f"  (no model access: {type(e).__name__}: {str(e)[:120]})")
        return False


def check_result(ws: str) -> bool:
    """Did the agent actually add multiply + a test, and do the tests pass?"""
    calc = _read(os.path.join(ws, "calc.py"))
    test = _read(os.path.join(ws, "test_calc.py"))
    has_fn = "def multiply" in calc
    has_test = "multiply" in test
    print(f"  multiply() added to calc.py: {has_fn}")
    print(f"  test references multiply:    {has_test}")
    passed = _run_pytest(ws)
    print(f"  pytest passes:               {passed}")
    return has_fn and has_test and passed


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _run_pytest(ws: str) -> bool:
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ws,
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0
    except Exception as e:
        print(f"  (could not run pytest: {e})")
        return False


def run(seed_only: bool) -> int:
    ws = tempfile.mkdtemp(prefix="dogfood_")
    print(f"workspace: {ws}")
    seed_project(ws)
    if not verify_seed(ws):
        print("FAIL: seeding failed.")
        return 1
    if seed_only:
        print("PASS: seed-only check (project seeded + verified). Run without --seed-only "
              "(with model keys) for the full read→edit→run loop.")
        return 0

    if not _model_available():
        print("SKIP: the full loop needs a working model key. Set one (e.g. "
              "GEMINI_API_KEY / NVIDIA_NIM_API_KEY / DEEPSEEK_API_KEY) and re-run. "
              "The seed + verification harness is validated.")
        return 2

    from core.orchestrator import handle_task
    budget = Budget(max_usd=1.0, max_iterations=24)
    print("running the agent on the task…")
    with tools.using_workspace(ws):
        final = handle_task(TASK, budget=budget, review="auto", acceptance=ACCEPTANCE)
    print(f"\nagent said: {(final or '')[:300]}\n")
    print(f"spent ${budget.spent_usd:.4f} over {budget.iterations} iterations")

    ok = check_result(ws)
    print("\n" + ("PASS: the platform added a feature + test and the suite is green."
                  if ok else "FAIL: the loop did not produce a passing feature (see above)."))
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-only", action="store_true",
                    help="only seed + verify the project (no model calls)")
    args = ap.parse_args()
    sys.exit(run(args.seed_only))
