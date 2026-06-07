#!/usr/bin/env python
"""
live_smoke.py — a SMALL real-model health check (complements the offline smoke test).

Unlike scripts/smoke_test.py (fake model, 60 checks, no keys), this fires a few REAL
calls through the actual pipeline to prove your provider key + model names work
end-to-end. It is deliberately tiny and rate-limit-friendly (paced for free tiers).

Run:
    python scripts/live_smoke.py            # uses .env keys + config/models.yaml
Exit code is non-zero if any live check fails. Cost is a few thousandths of a cent
on Gemini flash-lite; the run is capped by a Budget either way.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core.registry import registry
from core.llm import complete, Budget

PACE_SECONDS = float(os.environ.get("LIVE_SMOKE_PACE", "13"))  # > free-tier 5 RPM window
results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {str(e)[:160]}"
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  —  {detail}")


def _has_any_key():
    keys = ["GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_NIM_API_KEY"]
    return any(os.environ.get(k) and len(os.environ[k]) > 8 for k in keys)


def t1_chat():
    m = registry.model_for_tier("tier1", "chat")
    b = Budget(max_usd=0.05, max_iterations=4)
    resp, cost = complete(m, [{"role": "user", "content": "Reply with exactly one word: PONG"}],
                          budget=b, max_tokens=16)
    txt = (resp.choices[0].message.content or "").strip()
    return ("PONG" in txt.upper(), f"model={m} reply={txt!r} cost=${cost:.6f}")


def t1_routes():
    # the router is a real tier1 classification call
    from core.router import classify
    r = classify("Summarize this paragraph in one sentence.")
    tier = r.get("tier") if isinstance(r, dict) else getattr(r, "tier", None)
    return (tier in (1, 2, "tier1", "tier2"), f"router returned tier={tier}")


def main():
    print("\n  Live smoke — real model calls through the pipeline")
    if not _has_any_key():
        print("  SKIP: no provider key set in .env (this script needs one). "
              "Offline check: python scripts/smoke_test.py")
        sys.exit(2)
    print(f"  tier1={registry.model_for_tier('tier1')}  "
          f"tier2={registry.model_for_tier('tier2')}  (pacing {PACE_SECONDS}s between calls)\n")

    check("tier1 live chat returns content", t1_chat)
    time.sleep(PACE_SECONDS)
    check("router makes a real classification", t1_routes)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n  {passed}/{total} live checks passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
