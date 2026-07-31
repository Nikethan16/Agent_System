#!/usr/bin/env python
"""
sync_catalog.py — refresh config/models.synced.yaml from models.dev, on demand.

Pulls context windows, capability flags (tool-calling / vision / reasoning) and current
prices for the models ALREADY in your catalog, and writes them to the synced layer. Those
facts fill GAPS ONLY — your models.yaml always wins — so this is safe to run any time and
retires the LLM scout's guesswork on the factual fields.

    python -m scripts.sync_catalog          # (or: python scripts/sync_catalog.py)
    python -m scripts.sync_catalog --dry-run # show what would change, write nothing
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.registry import registry          # noqa: E402
from server import catalog_sync              # noqa: E402


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    dry = "--dry-run" in argv
    ids = [m["id"] for m in registry.catalog()]
    print(f"Syncing {len(ids)} catalog models from {catalog_sync.MODELS_DEV_URL} ...")
    try:
        res = catalog_sync.sync(ids)
    except Exception as e:                    # network/parse failure — never crash the caller
        print(f"  FAILED to fetch models.dev: {type(e).__name__}: {e}")
        return 1
    print(f"  matched  : {len(res['matched'])}")
    if res["unmatched"]:
        print(f"  unmatched: {len(res['unmatched'])} (left as-is) -> {res['unmatched']}")
    for mid in res["matched"]:
        f = res["models"][mid]
        price = f.get("synced_price")
        bits = [f"ctx={f['context_window']}"] if f.get("context_window") else []
        if price:
            bits.append(f"${price['input']}/${price['output']} per 1M")
        caps = [c for c in ("tool_call", "vision", "reasoning") if f.get(c)]
        if caps:
            bits.append("+".join(caps))
        print(f"    {mid:52s} {'  '.join(bits)}")
    if dry:
        print("  (dry-run — nothing written)")
        return 0
    path = catalog_sync.write_synced(res)
    print(f"  wrote    : {path}")
    print("  -> restart the server (or call registry.reload()) to pick up the new facts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
