#!/usr/bin/env python
"""
perf_battery.py — one round of REAL end-to-end testing across the task spectrum.

Runs a battery of live tasks through the actual pipeline (real models, real Docker
run_bash) and records, per task: route (tier / type / model), agents used, tools +
counts, fallbacks, retries, duration, cost, cache-hit %, verified?, and a short answer
snippet. Then a GLM-version bake-off (4.6 vs 5.1 vs 5.2) on one coding task.

    python -m scripts.perf_battery            # full battery + GLM bake-off
    python -m scripts.perf_battery battery     # battery only
    python -m scripts.perf_battery glm         # GLM bake-off only

Writes a plain-text report to data/perf_report.txt (and prints it).
"""
import os
import sys
import time
import json
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows console is cp1252
except Exception:
    pass
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core.llm import Budget
from core.orchestrator import handle_task
from core.registry import registry

REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "perf_report.txt")
_lines = []
def out(s=""):
    print(s)
    _lines.append(s)


BATTERY = [
    ("greeting",        "hi", 0.05, 6),
    ("simple-fact",     "What is the capital of France? Answer in one word.", 0.05, 6),
    ("reason-prose",    "In two sentences, explain why an AI system routes tasks into "
                        "difficulty tiers and uses cheaper models for easy work.", 0.15, 8),
    ("simple-code",     "Write a Python function is_prime(n) that returns True/False, then "
                        "run a quick check that is_prime(7) is True and is_prime(8) is False, "
                        "and report the real output.", 0.60, 18),
    ("research-web",    "Research the current best practices for prompt caching with LLM APIs "
                        "and summarize the top 3 points with sources.", 0.60, 12),
    ("complex-build",   "Build a command-line todo app in the workspace: todo.py with subcommands "
                        "add/list/done persisting to todos.json, plus test_todo.py (pytest) covering "
                        "add, list and done using a temp file. Run the tests with pytest, confirm they "
                        "pass, and report the exact command and its real output.", 1.20, 26),
]


def run_task(label, task, max_usd, max_iter):
    events = []
    b = Budget(max_usd=max_usd, max_iterations=max_iter)
    t0 = time.time()
    try:
        final = handle_task(task, budget=b, emit=events.append, review="auto")
    except Exception as e:
        final = f"(EXCEPTION: {type(e).__name__}: {e})"
    dur = round(time.time() - t0, 1)
    route = next((e for e in events if e.get("type") == "route"), {})
    agents = [e.get("agent") for e in events if e.get("type") == "assign"]
    tools = Counter(e.get("name") for e in events if e.get("type") == "tool")
    fb = [(e.get("from"), e.get("to")) for e in events if e.get("type") == "fallback"]
    retries = sum(1 for e in events if e.get("type") == "retry")
    cache_pct = (round(100 * b.cached_tokens / b.tokens) if b.tokens else 0)
    unver = isinstance(final, str) and "UNVERIFIED" in final
    return {
        "label": label, "tier": route.get("tier"), "type": route.get("task_type"),
        "model": route.get("routed_model"), "agents": agents, "tools": dict(tools),
        "fallbacks": fb, "retries": retries, "dur": dur, "cost": round(b.spent_usd, 5),
        "tokens": b.tokens, "cache_pct": cache_pct, "unverified": unver,
        "final": (final or "")[:150].replace("\n", " "),
    }


def print_row(r):
    out(f"\n[{r['label']}]  tier={r['tier']} type={r['type']}")
    out(f"  model(primary) : {r['model']}")
    out(f"  agents         : {r['agents']}")
    out(f"  tools          : {r['tools']}")
    out(f"  fallbacks      : {r['fallbacks']}   retries: {r['retries']}")
    out(f"  time={r['dur']}s  cost=${r['cost']}  tokens={r['tokens']}  cache={r['cache_pct']}%"
        + ("  UNVERIFIED" if r['unverified'] else ""))
    out(f"  answer         : {r['final']}")


def battery():
    out("=" * 78)
    out("PERFORMANCE BATTERY — real pipeline, current combination")
    out("=" * 78)
    rows = [run_task(*t) for t in BATTERY]
    for r in rows:
        print_row(r)
    out("\n--- summary ---")
    out(f"{'task':<16}{'tier':<6}{'model':<40}{'time':>7}{'cost':>9}{'cache':>7}")
    for r in rows:
        m = (r['model'] or '')[-38:]
        out(f"{r['label']:<16}{str(r['tier']):<6}{m:<40}{r['dur']:>6}s${r['cost']:>8}{r['cache_pct']:>6}%")
    total = round(sum(r['cost'] for r in rows), 4)
    out(f"\nBATTERY TOTAL COST: ${total}")
    return rows


def glm_bakeoff():
    out("\n" + "=" * 78)
    out("GLM VERSION BAKE-OFF — same coding task, coding chain pinned to each GLM")
    out("=" * 78)
    task = ("Write fizzbuzz.py in the workspace: a function fizzbuzz(n) returning 'Fizz'/'Buzz'/"
            "'FizzBuzz'/str(n) per the classic rules, plus a check that runs fizzbuzz(3)=='Fizz', "
            "fizzbuzz(5)=='Buzz', fizzbuzz(15)=='FizzBuzz', fizzbuzz(2)=='2' and prints OK. "
            "Run it and report the real output.")
    versions = ["deepinfra/zai-org/GLM-4.6", "deepinfra/zai-org/GLM-5.1", "deepinfra/zai-org/GLM-5.2"]
    saved = registry.routing_overrides().get("coding")
    results = []
    for v in versions:
        registry.set_routing("coding", [v])
        r = run_task(f"glm::{v.split('/')[-1]}", task, 0.60, 18)
        results.append((v, r))
        print_row(r)
    # restore
    if saved is not None:
        registry.set_routing("coding", saved)
    else:
        registry.reset_routing("coding")
    out("\n--- GLM comparison ---")
    out(f"{'version':<12}{'time':>7}{'cost':>9}{'cache':>7}  verified")
    for v, r in results:
        out(f"{v.split('/')[-1]:<12}{r['dur']:>6}s${r['cost']:>8}{r['cache_pct']:>6}%  "
            + ("no (UNVERIFIED)" if r['unverified'] else "yes"))
    return results


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "battery"):
        battery()
    if mode in ("all", "glm"):
        glm_bakeoff()
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))
    out(f"\nreport written: {REPORT}")
