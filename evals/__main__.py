"""
__main__.py — one-command entry point.

  python -m evals                         # real run against the active models.yaml
  python -m evals --dry-run               # free practice mode (no keys, no cost)
  python -m evals --filter write          # only cases whose id contains "write"
  python -m evals --config path.yaml      # run against an alternate model config
  python -m evals --compare A.yaml B.yaml # run both, print a side-by-side diff
  python -m evals --max-usd 1.0           # override the suite-wide spend ceiling

Exit code is 0 when the pass-rate meets the suite threshold (1 otherwise), so
this works as a CI gate. In compare mode, exit code is 1 if there are regressions.
"""
import os
import sys
import argparse

from .runner import run_suite, compare
from . import report

DEFAULT_CASES = os.path.join(os.path.dirname(__file__), "cases.yaml")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m evals",
                                description="Run the agent-core eval suite.")
    p.add_argument("--cases", default=DEFAULT_CASES, help="path to cases.yaml")
    p.add_argument("--config", default=None, help="alternate models.yaml to run against")
    p.add_argument("--filter", default=None, help="only run cases whose id contains this")
    p.add_argument("--dry-run", action="store_true",
                   help="use deterministic fake answers (no API keys, no cost)")
    p.add_argument("--compare", nargs=2, metavar=("A.yaml", "B.yaml"),
                   help="run the suite against two configs and diff them")
    p.add_argument("--max-usd", type=float, default=None,
                   help="override the suite-wide spend ceiling")
    args = p.parse_args(argv)

    if args.compare:
        run_a, run_b = compare(args.cases, args.compare[0], args.compare[1],
                               dry_run=args.dry_run, filter=args.filter,
                               max_usd=args.max_usd)
        report.print_run(run_a)
        report.print_run(run_b)
        regressions = report.print_compare(run_a, run_b)
        path = report.write_report({"mode": "compare", "A": run_a, "B": run_b})
        print(f"  report written: {path}")
        return 1 if regressions else 0

    run = run_suite(args.cases, config_path=args.config, filter=args.filter,
                    dry_run=args.dry_run, max_usd=args.max_usd)
    report.print_run(run)
    path = report.write_report({"mode": "single", "run": run})
    print(f"  report written: {path}")
    # --dry-run uses simulated answers, so the pass-rate is meaningless — its job is to
    # validate that the harness LOADS + RUNS every case offline. Exit 0 once it has
    # (so it works as a CI smoke of the harness itself); real runs gate on the threshold.
    if args.dry_run:
        return 0
    return report.exit_code_for(run)


if __name__ == "__main__":
    sys.exit(main())
