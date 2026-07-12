"""
graders.py — concrete yes/no checks. NO 1-10 scores anywhere (project rule:
judge on real pass/fail facts — does it run? right file? expected words?).

Every grader has the signature:
    grade(spec, output, ctx) -> (passed: bool, reason: str)
where `spec` is the grader dict from cases.yaml, `output` is the agent's final
answer, and `ctx` carries {workspace, events, tier, budget}.

A case passes only if ALL of its graders pass (see run_graders).
"""
import os
import re
import sys
import json
import subprocess

# core.tools fixes WORKSPACE at import time from AGENT_WORKSPACE, which the
# evals package sets before any core import. Reuse it as the single source of
# truth for where eval files land.
from core.tools import WORKSPACE
from core.llm import complete, BudgetExceeded
from core.registry import registry


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


# ---- text graders ---------------------------------------------------------
def grade_contains(spec, output, ctx):
    out = (output or "").lower()
    any_terms = [t.lower() for t in _as_list(spec.get("any"))]
    all_terms = [t.lower() for t in _as_list(spec.get("all"))]
    if any_terms and not any(t in out for t in any_terms):
        return False, f"none of {spec.get('any')} found"
    missing = [t for t in all_terms if t not in out]
    if missing:
        return False, f"missing required: {missing}"
    return True, "expected terms present"


def grade_not_contains(spec, output, ctx):
    out = (output or "").lower()
    terms = [t.lower() for t in _as_list(spec.get("any")) + _as_list(spec.get("all"))]
    present = [t for t in terms if t in out]
    if present:
        return False, f"forbidden terms present: {present}"
    return True, "no forbidden terms"


def grade_regex(spec, output, ctx):
    pattern = spec["pattern"]
    flags = re.IGNORECASE if spec.get("ignorecase", True) else 0
    if re.search(pattern, output or "", flags):
        return True, f"matched /{pattern}/"
    return False, f"no match for /{pattern}/"


# ---- workspace file/shell graders -----------------------------------------
def _wpath(path):
    """Resolve a path inside the eval workspace (refuse escapes)."""
    full = os.path.abspath(os.path.join(WORKSPACE, path))
    if not full.startswith(WORKSPACE):
        raise ValueError("path escapes workspace")
    return full


def grade_file_exists(spec, output, ctx):
    full = _wpath(spec["path"])
    if not os.path.isfile(full):
        return False, f"file not found: {spec['path']}"
    if spec.get("non_empty", True) and os.path.getsize(full) == 0:
        return False, f"file is empty: {spec['path']}"
    return True, f"file exists: {spec['path']}"


def grade_file_contains(spec, output, ctx):
    full = _wpath(spec["path"])
    if not os.path.isfile(full):
        return False, f"file not found: {spec['path']}"
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            content = f.read().lower()
    except Exception as e:
        return False, f"could not read {spec['path']}: {e}"
    needed = [t.lower() for t in _as_list(spec.get("all")) + _as_list(spec.get("contains"))]
    missing = [t for t in needed if t not in content]
    if missing:
        return False, f"{spec['path']} missing: {missing}"
    return True, f"{spec['path']} contains expected text"


def grade_bash_check(spec, output, ctx):
    cmd = spec["command"]
    expect = spec.get("expect_exit", 0)
    # Run a bare `python`/`python3` with the SAME interpreter running the evals (it has
    # pytest + the project deps). A shell `python` would otherwise resolve to whatever is
    # first on PATH — often a system Python without the test tooling (a false FAIL).
    cmd = re.sub(r"\bpython3?\b", lambda _m: f'"{sys.executable}"', cmd, count=1)
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=WORKSPACE,
            capture_output=True, text=True,
            timeout=spec.get("timeout", 30),
        )
    except Exception as e:
        return False, f"command errored: {e}"
    if proc.returncode != expect:
        tail = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[-160:]
        return False, f"`{cmd}` exit={proc.returncode} (want {expect}): {tail}"
    return True, f"`{cmd}` exit={proc.returncode}"


# ---- optional AI judge (binary verdict only) ------------------------------
JUDGE_SYS = (
    "You are a strict grader. Decide whether the ANSWER satisfies the CRITERIA.\n"
    "Output ONLY valid JSON, no prose, no code fences:\n"
    '{"pass": true|false, "reason": "<=20 words"}\n'
    "Do NOT output a numeric score or rating. The verdict is binary: pass or fail."
)


def grade_llm_judge(spec, output, ctx):
    # Model resolved via the registry — never hardcoded. Prefer a configured
    # judge_tier if present, else the fallback tier.
    judge_tier = registry.cfg.get("defaults", {}).get("judge_tier") or registry.fallback_tier()
    model = registry.model_for_tier(judge_tier)
    prompt = f"CRITERIA:\n{spec['criteria']}\n\nANSWER:\n{output or '(empty)'}"
    try:
        # Shares the case Budget, so the judge call is capped like everything else.
        resp, _ = complete(
            model,
            [{"role": "system", "content": JUDGE_SYS},
             {"role": "user", "content": prompt}],
            max_tokens=200, budget=ctx.get("budget"), temperature=0,
        )
    except BudgetExceeded as e:
        return False, f"judge skipped: {e}"
    except Exception as e:
        return False, f"judge errored: {type(e).__name__}: {e}"
    txt = (resp.choices[0].message.content or "").strip()
    try:
        data = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        return bool(data["pass"]), f"judge[{judge_tier}]: {data.get('reason', '')}"
    except Exception:
        return False, f"judge: unparseable verdict: {txt[:80]!r}"


GRADERS = {
    "contains": grade_contains,
    "not_contains": grade_not_contains,
    "regex": grade_regex,
    "file_exists": grade_file_exists,
    "file_contains": grade_file_contains,
    "bash_check": grade_bash_check,
    "llm_judge": grade_llm_judge,
}


def run_graders(case, output, ctx):
    """
    Run every grader for a case plus the optional expect_tier check.
    Returns (passed_all, results) where results is a list of (name, ok, reason).
    A case with no checks fails loudly rather than passing vacuously.
    """
    results = []

    expect_tier = case.get("expect_tier")
    if expect_tier is not None:
        got = ctx.get("tier")
        ok = (got == int(expect_tier))
        results.append(("expect_tier", ok, f"routed tier{got} vs expected tier{expect_tier}"))

    for spec in case.get("graders", []):
        gtype = spec.get("type")
        fn = GRADERS.get(gtype)
        if not fn:
            results.append((gtype or "?", False, f"unknown grader type: {gtype!r}"))
            continue
        try:
            ok, reason = fn(spec, output, ctx)
        except KeyError as e:
            ok, reason = False, f"grader spec missing field {e}"
        except Exception as e:
            ok, reason = False, f"grader crashed: {type(e).__name__}: {e}"
        results.append((gtype, ok, reason))

    passed_all = bool(results) and all(ok for _, ok, _ in results)
    return passed_all, results
