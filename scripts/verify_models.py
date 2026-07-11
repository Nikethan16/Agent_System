#!/usr/bin/env python
"""
verify_models.py — smoke-test every catalog model whose provider key is present.

Provider catalogs rename models within weeks, and a wrong id in config/models.yaml
fails SILENTLY (model_chain just skips it and falls through). This script does ONE
cheap real call per available model and reports which ids are valid vs renamed/404 —
run it the moment a new key lands (DeepSeek, DeepInfra, …) to de-risk the rollout.

Usage:
    python -m scripts.verify_models              # verify every keyed model
    python -m scripts.verify_models --json       # machine-readable output
    python -m scripts.verify_models deepseek     # only ids containing "deepseek"

Exit code is non-zero if any AVAILABLE model failed (so it works as a CI/rollout gate).
Models whose requires_env key is unset are SKIPPED (not failed) — offline-safe.
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core.registry import registry
from core.llm import complete, Budget


def _available(entry: dict) -> bool:
    env = entry.get("requires_env")
    return (not env) or bool(os.environ.get(env))


def verify_one(model_id: str) -> dict:
    """One minimal call. Returns {id, ok, latency_s, detail}."""
    t0 = time.time()
    try:
        # 1 token, tiny prompt — cheapest possible liveness probe.
        resp, cost = complete(
            model_id,
            [{"role": "user", "content": "Reply with the single word: ok"}],
            max_tokens=5, budget=Budget(max_usd=0.05, max_iterations=2), temperature=0,
        )
        txt = (resp.choices[0].message.content or "").strip()
        return {"id": model_id, "ok": True, "latency_s": round(time.time() - t0, 1),
                "detail": txt[:40] or "(empty)", "cost": round(cost, 6)}
    except Exception as e:
        return {"id": model_id, "ok": False, "latency_s": round(time.time() - t0, 1),
                "detail": f"{type(e).__name__}: {str(e)[:160]}"}


def main(argv):
    want = [a for a in argv if not a.startswith("-")]
    as_json = "--json" in argv

    catalog = registry.catalog()
    results, skipped = [], []
    for entry in catalog:
        mid = entry.get("id")
        if not mid:
            continue
        if want and not any(w.lower() in mid.lower() for w in want):
            continue
        if not _available(entry):
            skipped.append({"id": mid, "requires_env": entry.get("requires_env")})
            continue
        results.append(verify_one(mid))

    if as_json:
        print(json.dumps({"verified": results, "skipped": skipped}, indent=2))
    else:
        print("\n=== MODEL VERIFICATION ===")
        for r in results:
            mark = "OK  " if r["ok"] else "FAIL"
            print(f"  [{mark}] {r['id']:<48} {r['latency_s']:>5}s  {r['detail']}")
        for s in skipped:
            print(f"  [skip] {s['id']:<48} (no {s['requires_env']})")
        ok_n = sum(1 for r in results if r["ok"])
        print(f"\n{ok_n}/{len(results)} available models OK · {len(skipped)} skipped (no key)")

    return 1 if any(not r["ok"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
