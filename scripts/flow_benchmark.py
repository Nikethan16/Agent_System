#!/usr/bin/env python
"""
flow_benchmark.py — measure the REAL workflow on the two scenarios that motivated
the optimization: a greeting ("hi") and a single-file build ("build a calculator app").

Runs each prompt through the actual orchestrator pipeline, captures every emitted
event, and prints a per-scenario scorecard: routed tier + model, how many agents/
delegations/tool-calls/fallbacks/denials happened, plus iterations, tokens, wall-clock,
and whether the run COMPLETED (vs hit the iteration cap). This is how we turn the
"53m / 130k tokens / cap hit" baseline into concrete after-numbers.

Run on the VM (needs a provider key in .env; the Docker sandbox enables run_bash):
    python scripts/flow_benchmark.py
    python scripts/flow_benchmark.py --only calculator      # one scenario
    python scripts/flow_benchmark.py --max-usd 0.25 --max-iter 24
"""
import os
import sys
import time
import argparse
from collections import Counter

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
# Isolate file side-effects from the live ./workspace. Set BEFORE importing core.tools.
os.environ.setdefault("AGENT_WORKSPACE", os.path.join(_ROOT, "data", "_flowbench_ws"))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core.registry import registry
from core.llm import Budget
from core.orchestrator import handle_task
from core import toolbelt

SCENARIOS = {
    "greeting": "hi",
    "calculator": "build a simple calculator web app (single HTML file)",
}


def _has_key():
    keys = ["GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_NIM_API_KEY"]
    return any(os.environ.get(k) and len(os.environ[k]) > 8 for k in keys)


def run_scenario(name, prompt, max_usd, max_iter):
    events = []

    def emit(ev):
        events.append(ev)
        t = ev.get("type")
        # live trace so you can watch it work
        if t == "route":
            print(f"    route → tier {ev.get('tier')} / {ev.get('task_type')} "
                  f"[{ev.get('routed_model','?')}]")
        elif t == "assign":
            print(f"    assign → {ev.get('agent')} [{ev.get('model','?')}]")
        elif t == "plan":
            print(f"    plan → {len(ev.get('subtasks', []))} step(s)")
        elif t == "tool":
            print(f"    tool → {ev.get('name')}")
        elif t == "fallback":
            print(f"    fallback → {ev.get('from')} → {ev.get('to')}  ({ev.get('reason','')[:50]})")
        elif t in ("denied", "blocked"):
            print(f"    {t} → {ev.get('name')}: {ev.get('reason','')[:60]}")
        elif t == "manager_review":
            print(f"    manager_review → {ev.get('tool')}: approved={ev.get('approved')}")
        elif t == "critic":
            print(f"    critic → pass={ev.get('passed')}")

    budget = Budget(max_usd=max_usd, max_iterations=max_iter)
    print(f"\n  ── {name}: {prompt!r}")
    t0 = time.time()
    try:
        final = handle_task(prompt, budget=budget, emit=emit, approve=None, review="auto")
        err = None
    except Exception as e:
        final, err = "", f"{type(e).__name__}: {e}"
    elapsed = time.time() - t0

    kinds = Counter(e.get("type") for e in events)
    route = next((e for e in events if e.get("type") == "route"), {})
    completed = budget.iterations < budget.max_iterations and not err
    cap_hit = budget.iterations >= budget.max_iterations

    print(f"  ── result:")
    print(f"       tier         {route.get('tier','?')} ({route.get('task_type','?')})")
    print(f"       agents       {kinds.get('assign', 0)}  delegations={kinds.get('plan', 0)} plan(s)")
    print(f"       tool calls   {kinds.get('tool', 0)}")
    print(f"       fallbacks    {kinds.get('fallback', 0)}   denied={kinds.get('denied', 0)}   "
          f"blocked={kinds.get('blocked', 0)}")
    print(f"       iterations   {budget.iterations}/{budget.max_iterations}"
          f"{'  ⚠ CAP HIT' if cap_hit else ''}")
    print(f"       tokens       {budget.tokens:,}")
    print(f"       cost         ${budget.spent_usd:.5f}")
    print(f"       wall-clock   {elapsed:.1f}s")
    print(f"       completed    {'YES' if completed else 'NO'}{'  err=' + err if err else ''}")
    if final:
        print(f"       answer       {final[:140].strip()!r}")

    return {
        "name": name, "tier": route.get("tier"), "agents": kinds.get("assign", 0),
        "tools": kinds.get("tool", 0), "fallbacks": kinds.get("fallback", 0),
        "denied": kinds.get("denied", 0), "iterations": budget.iterations,
        "tokens": budget.tokens, "cost": budget.spent_usd, "seconds": elapsed,
        "completed": completed, "cap_hit": cap_hit,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(SCENARIOS), help="run a single scenario")
    ap.add_argument("--max-usd", type=float, default=0.25)
    ap.add_argument("--max-iter", type=int, default=24)
    args = ap.parse_args()

    if not _has_key():
        print("  SKIP: no provider key in .env — this script makes real model calls.")
        sys.exit(2)

    print("\n  Flow benchmark — real pipeline on the optimization's two scenarios")
    print(f"  tier1={registry.model_for_tier('tier1')}  tier2={registry.model_for_tier('tier2')}  "
          f"tier3={registry.model_for_tier('tier3')}")
    print(f"  run_bash available: {'YES (sandbox live)' if 'run_bash' in toolbelt.names() else 'NO (Docker not set)'}")

    todo = {args.only: SCENARIOS[args.only]} if args.only else SCENARIOS
    rows = [run_scenario(n, p, args.max_usd, args.max_iter) for n, p in todo.items()]

    print("\n  ── summary ──────────────────────────────────────────────")
    print(f"  {'scenario':<12}{'tier':>5}{'iters':>7}{'tokens':>10}{'secs':>7}{'done':>6}")
    for r in rows:
        print(f"  {r['name']:<12}{str(r['tier']):>5}{r['iterations']:>7}"
              f"{r['tokens']:>10,}{r['seconds']:>7.0f}{('Y' if r['completed'] else 'N'):>6}")
    print()
    print("  Baseline before this work (calculator): tier 3, 20 iters (CAP HIT),")
    print("  130,575 tokens, 53m 22s, did NOT complete. Compare above.")


if __name__ == "__main__":
    main()
