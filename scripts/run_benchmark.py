"""
run_benchmark.py — score one model on the benchmark battery, in ISOLATION.

Runs in its own process so it can (a) pin every tier to the target model and
(b) use a dedicated scratch workspace, WITHOUT touching the live app's registry
or ./workspace or any chat session. The server spawns this and reads the JSON it
writes to --out.

    python scripts/run_benchmark.py --model gemini/gemini-2.5-flash --mode both --out r.json
    python scripts/run_benchmark.py --model x --mode both --out r.json --dry-run   # offline plumbing test
"""
import os
import sys
import json
import time
import shutil
import argparse

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
# Isolate file/shell side-effects from the live ./workspace and chat sessions.
# Must be set BEFORE importing core.tools (which fixes WORKSPACE at import time).
os.environ["AGENT_WORKSPACE"] = os.path.join(_ROOT, "data", "_bench_ws")

import yaml
from core.tools import WORKSPACE
from core.llm import Budget
from core.agent import run_agent
from core import toolbelt
from core.orchestrator import handle_task
from core.registry import registry
from evals.graders import run_graders
from evals.runner import _maybe_dry_run

_SUITE = os.path.join(_ROOT, "evals", "benchmark.yaml")

RAW_SYS = (
    "You are a capable assistant with file and shell tools (read_file, write_file, "
    "edit_file, list_files, run_bash). Complete the task fully: create or edit files "
    "and run code/commands as needed, then give a concise final answer."
)


def _clean():
    os.makedirs(WORKSPACE, exist_ok=True)
    for n in os.listdir(WORKSPACE):
        p = os.path.join(WORKSPACE, n)
        try:
            shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
        except OSError:
            pass


def _force_model(model: str):
    """Pin every tier to `model` (fixed strategy) for the pipeline runs."""
    registry.cfg.setdefault("defaults", {})["model_strategy"] = "fixed"
    for t in registry.cfg.get("tiers", {}):
        registry.cfg["tiers"][t]["model"] = model


def _run_case(case, mode, model, budget):
    _clean()
    events = []
    try:
        if mode == "raw":
            out = run_agent(case["task"], RAW_SYS, model, budget=budget,
                            emit=events.append, allowed_tools=toolbelt.names())
        else:  # pipeline
            out = handle_task(case["task"], budget=budget, emit=events.append, review=False)
    except Exception as e:
        out = f"(run error: {type(e).__name__}: {e})"
    ok, _results = run_graders(
        case, out, {"workspace": WORKSPACE, "events": events, "tier": None, "budget": budget})
    return bool(ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--mode", default="both", choices=["raw", "pipeline", "both"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(_SUITE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    suite, cases = data.get("suite", {}) or {}, data.get("cases", []) or []
    per = suite.get("default_max_usd", 0.15)
    iters = suite.get("default_max_iterations", 12)
    ceiling = suite.get("max_usd", 2.0)

    modes = ["raw", "pipeline"] if args.mode == "both" else [args.mode]
    if "pipeline" in modes:
        _force_model(args.model)

    scores = {m: {} for m in modes}
    cost, t0, err = 0.0, time.time(), ""
    try:
        with _maybe_dry_run(args.dry_run):
            for m in modes:
                for c in cases:
                    asp = c.get("aspect", "other")
                    d = scores[m].setdefault(asp, {"passed": 0, "total": 0})
                    d["total"] += 1
                    if cost >= ceiling:          # hard suite-wide spend brake
                        continue
                    b = Budget(max_usd=per, max_iterations=iters)
                    if _run_case(c, m, args.model, b):
                        d["passed"] += 1
                    cost += b.spent_usd
    except Exception as e:
        err = f"{type(e).__name__}: {e}"

    result = {"model": args.model, "mode": args.mode, "scores": scores,
              "cost": round(cost, 6), "duration": round(time.time() - t0, 2), "error": err}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
