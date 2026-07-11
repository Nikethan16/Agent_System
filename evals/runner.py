"""
runner.py — runs eval cases through the REAL pipeline, grades them, aggregates.

Responsibilities:
  * load cases.yaml
  * isolate a clean workspace per case (so file/bash graders are reliable)
  * run each case under its own Budget (per-case caps) with a suite-wide spend brake
  * (optional) dry-run: swap the model call for a deterministic fake — no keys/cost
  * support running against an alternate models.yaml, and A/B comparing two configs

This module imports core but lives outside it; core is never modified. The
dry-run monkeypatch is applied from here, never inside core/.
"""
import os
import time
import shutil
import contextlib

import yaml

# evals/__init__.py set AGENT_WORKSPACE before this import chain, so WORKSPACE
# below points at the isolated eval workspace.
from core.tools import WORKSPACE
from core.registry import registry
from core.llm import Budget
from core.orchestrator import handle_task

from .graders import run_graders


def load_suite(path):
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("suite", {}) or {}, data.get("cases", []) or []


def _clean_workspace():
    """Wipe the eval workspace so one case can't see another's files."""
    os.makedirs(WORKSPACE, exist_ok=True)
    for name in os.listdir(WORKSPACE):
        p = os.path.join(WORKSPACE, name)
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        except OSError:
            pass


# ---------------------------------------------------------------------------
#  Dry-run fake: a deterministic stand-in for litellm.completion. It proves the
#  harness wiring (route -> worker -> final, grading, reporting) with no API
#  keys and zero cost. It does NOT judge answer quality — cases may "fail".
# ---------------------------------------------------------------------------
class _FakeMessage:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None

    def model_dump(self):
        return {"role": "assistant", "content": self.content}


class _FakeResp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": _FakeMessage(content)})()]
        self._hidden_params = {"response_cost": 0.0}


def _fake_completion(**kwargs):
    system = ""
    for m in kwargs.get("messages", []):
        if m.get("role") == "system":
            system = m.get("content", "") or ""
            break
    if "subtasks" in system:                                   # planner
        content = '{"subtasks": ["[dry-run] handle the task"]}'
    elif "task router" in system or '"tier"' in system:        # router/classifier
        content = '{"tier": 1, "task_type": "writing", "requires_web": false, "reason": "dry-run"}'
    else:                                                       # worker / synth / judge
        content = "[dry-run] simulated answer; no real model was called."
    return _FakeResp(content)


@contextlib.contextmanager
def _maybe_dry_run(enabled):
    if not enabled:
        yield
        return
    import core.llm as llm_mod
    original = llm_mod.litellm.completion
    llm_mod.litellm.completion = _fake_completion
    try:
        yield
    finally:
        llm_mod.litellm.completion = original


def _routed_tier(events):
    # The routing event has type=="route" and also carries a unique
    # "routed_model" key. We accept either: the type check is the contract, and
    # "routed_model" stays as a belt-and-suspenders fallback.
    for ev in events:
        if ev.get("type") == "route" or "routed_model" in ev:
            return ev.get("tier")
    return None


def _seed_workspace(case):
    """Pre-create files a case needs BEFORE the agent runs (`setup.files:` in the case:
    a {relative_path: content} map). Lets a case test 'fix this existing file' instead of
    only 'build from scratch'. Paths are confined to the eval workspace."""
    files = ((case.get("setup") or {}).get("files")) or {}
    for rel, content in files.items():
        full = os.path.normpath(os.path.join(WORKSPACE, rel))
        if not full.startswith(os.path.abspath(WORKSPACE)):
            raise ValueError(f"setup file escapes workspace: {rel}")
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else str(content))


def run_case(case, suite):
    """Run one case (assumes any dry-run patch is already active) and grade it."""
    _clean_workspace()
    _seed_workspace(case)
    cb = case.get("budget", {}) or {}
    budget = Budget(
        max_usd=cb.get("max_usd", suite.get("default_max_usd", 0.50)),
        max_iterations=cb.get("max_iterations", suite.get("default_max_iterations", 8)),
    )

    events, error, output = [], None, ""
    start = time.time()
    try:
        output = handle_task(case["task"], budget=budget, emit=events.append)
    except Exception as e:  # a crashing case fails that case, not the suite
        error = f"{type(e).__name__}: {e}"
    duration = time.time() - start

    tier = _routed_tier(events)
    ctx = {"workspace": WORKSPACE, "events": events, "tier": tier, "budget": budget}

    if error:
        passed, results = False, [("run", False, error)]
    else:
        passed, results = run_graders(case, output, ctx)

    return {
        "id": case.get("id", "?"),
        "passed": passed,
        "tier": tier,
        "cost": round(budget.spent_usd, 6),
        "iterations": budget.iterations,
        "duration": round(duration, 2),
        "results": results,
        "error": error,
    }


def run_suite(cases_path, config_path=None, filter=None, dry_run=False, max_usd=None):
    """Run the full suite once against one model config. Returns a result dict."""
    if config_path:
        registry.path = config_path
        registry.reload()

    suite, cases = load_suite(cases_path)
    if filter:
        cases = [c for c in cases if filter in c.get("id", "")]

    ceiling = max_usd if max_usd is not None else suite.get("max_usd", 5.0)
    snapshot = {t: registry.model_for_tier(t) for t in registry.cfg.get("tiers", {})}

    results, spent = [], 0.0
    with _maybe_dry_run(dry_run):
        for case in cases:
            if spent >= ceiling:
                results.append({
                    "id": case.get("id", "?"), "passed": False, "tier": None,
                    "cost": 0.0, "iterations": 0, "duration": 0.0,
                    "results": [("suite", False, f"skipped: ${ceiling} spend ceiling reached")],
                    "error": "skipped (budget ceiling)",
                })
                continue
            r = run_case(case, suite)
            spent += r["cost"]
            results.append(r)

    return {
        "config": config_path or registry.path,
        "models": snapshot,
        "dry_run": dry_run,
        "total_cost": round(spent, 6),
        "pass_threshold": suite.get("pass_threshold", 1.0),
        "results": results,
    }


def compare(cases_path, config_a, config_b, dry_run=False, **kw):
    """Run the suite against two configs (sequentially) for side-by-side diffing."""
    run_a = run_suite(cases_path, config_path=config_a, dry_run=dry_run, **kw)
    run_b = run_suite(cases_path, config_path=config_b, dry_run=dry_run, **kw)
    return run_a, run_b
