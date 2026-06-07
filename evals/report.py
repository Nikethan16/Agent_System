"""
report.py — render results to the console, write a JSON report, decide exit code.

The console output always leads with the MODEL SNAPSHOT (which model served each
tier), because eval results are only meaningful relative to the config they ran
against — that's the whole point of the harness.
"""
import os
import json
from datetime import datetime, timezone

REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")


def _fmt_models(models):
    return ", ".join(f"{t}={m}" for t, m in models.items())


def _first_fail_reason(r):
    for name, ok, reason in r.get("results", []):
        if not ok:
            return f"[{name}] {reason}"
    if r.get("results"):  # all passed — show the last note
        return r["results"][-1][2]
    return ""


def print_run(run):
    mode = "DRY-RUN (fake answers)" if run["dry_run"] else "REAL"
    print()
    print(f"  Eval run [{mode}]   config: {run['config']}")
    print(f"  Models: {_fmt_models(run['models'])}")
    print("  " + "-" * 84)
    print(f"  {'CASE':<22}{'TIER':<6}{'RESULT':<8}{'COST $':<11}{'ITERS':<7}REASON")
    print("  " + "-" * 84)
    for r in run["results"]:
        tier = f"t{r['tier']}" if r["tier"] else "-"
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  {r['id']:<22}{tier:<6}{status:<8}{r['cost']:<11.5f}"
              f"{r['iterations']:<7}{_first_fail_reason(r)}")
    passed = sum(1 for r in run["results"] if r["passed"])
    total = len(run["results"])
    print("  " + "-" * 84)
    print(f"  {passed}/{total} passed    total cost ${run['total_cost']:.5f}")
    print()


def print_compare(run_a, run_b):
    print()
    print("  A/B COMPARISON")
    print(f"  A: {_fmt_models(run_a['models'])}")
    print(f"  B: {_fmt_models(run_b['models'])}")
    print("  " + "-" * 84)
    print(f"  {'CASE':<22}{'A':<7}{'B':<7}{'A $':<11}{'B $':<11}NOTE")
    print("  " + "-" * 84)
    b_by_id = {r["id"]: r for r in run_b["results"]}
    regressions = 0
    for ra in run_a["results"]:
        rb = b_by_id.get(ra["id"], {})
        a_ok, b_ok = ra["passed"], rb.get("passed", False)
        note = ""
        if a_ok and not b_ok:
            note, regressions = "*** REGRESSION ***", regressions + 1
        elif b_ok and not a_ok:
            note = "improvement"
        print(f"  {ra['id']:<22}{('PASS' if a_ok else 'FAIL'):<7}"
              f"{('PASS' if b_ok else 'FAIL'):<7}{ra['cost']:<11.5f}"
              f"{rb.get('cost', 0.0):<11.5f}{note}")
    pa = sum(1 for r in run_a["results"] if r["passed"])
    pb = sum(1 for r in run_b["results"] if r["passed"])
    print("  " + "-" * 84)
    print(f"  A: {pa}/{len(run_a['results'])} passed  ${run_a['total_cost']:.5f}     "
          f"B: {pb}/{len(run_b['results'])} passed  ${run_b['total_cost']:.5f}")
    print(f"  regressions (passed in A, failed in B): {regressions}")
    print()
    return regressions


def write_report(payload):
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(REPORT_DIR, f"{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return path


def exit_code_for(run):
    total = len(run["results"]) or 1
    passed = sum(1 for r in run["results"] if r["passed"])
    return 0 if (passed / total) >= run["pass_threshold"] else 1
