"""
catalog_sync.py — DETERMINISTIC model-catalog refresh from models.dev.

The LLM model-scout *guesses* at catalog facts (context window, capabilities, price);
this pulls them from a cited source instead. It fetches https://models.dev/api.json
(a community catalog of ~100 providers / thousands of models), matches each model
ALREADY in Nikki's catalog by slug, and writes the facts to config/models.synced.yaml.

Two deliberate design rules:
  1. Facts FILL GAPS ONLY. The registry merges this UNDER your models.yaml — a hand-set
     value always wins, so a sync can never clobber curation (see registry.catalog()).
  2. NO DOLLAR PRICES land in models.yaml (Nikki's "no stale prices in the repo" rule).
     Prices are stored in the *synced* layer as informational `synced_price`, plus a coarse
     `cost` RANK derived from them (also a gap-filler — your ranks win).

Lives OUTSIDE core/ because it makes a network call; core/ stays offline and only READS
the file this writes. Trigger it on demand: `python -m scripts.sync_catalog`.
"""
import os
import json
import datetime
import urllib.request

import yaml

MODELS_DEV_URL = os.environ.get("MODELS_DEV_URL", "https://models.dev/api.json")
_DIR = os.path.dirname(os.path.abspath(__file__))
SYNCED_PATH = os.environ.get(
    "MODELS_SYNCED", os.path.join(_DIR, "..", "config", "models.synced.yaml"))


def fetch_models_dev(url: str = MODELS_DEV_URL, timeout: int = 20) -> dict:
    """GET models.dev/api.json. The URL is a FIXED, known host (never user-supplied), so
    there is no SSRF surface here. Raises on network/parse failure — the caller decides."""
    req = urllib.request.Request(url, headers={"User-Agent": "nikki-catalog-sync/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:      # nosec B310 - fixed https host
        return json.loads(r.read().decode("utf-8"))


def _norm(s) -> str:
    return str(s or "").strip().lower()


def build_index(api: dict) -> dict:
    """Flatten models.dev into {normalized model slug -> facts} across every provider, so a
    model can be matched regardless of which vendor/host serves it. First occurrence of a
    slug wins (stable), which is fine — the FACTS (context/capabilities) are host-invariant."""
    idx: dict[str, dict] = {}
    for prov in (api or {}).values():
        if not isinstance(prov, dict):
            continue
        for slug, m in (prov.get("models") or {}).items():
            if not isinstance(m, dict):
                continue
            limit = m.get("limit") or {}
            modal = m.get("modalities") or {}
            cost = m.get("cost") or {}
            facts = {
                "context_window": limit.get("context"),
                "tool_call": m.get("tool_call"),
                "reasoning": m.get("reasoning"),
                "vision": bool(m.get("attachment")) or ("image" in (modal.get("input") or [])),
                "price_in": cost.get("input"),
                "price_out": cost.get("output"),
            }
            for key in {_norm(slug), _norm(m.get("id"))}:
                if key and key not in idx:
                    idx[key] = facts
    return idx


def _candidate_keys(mid) -> list:
    """Slugs to try for a Nikki model id, best first. The last path segment, plus a
    tag-stripped variant so OpenRouter `:free` and Ollama `:8b` style suffixes still match."""
    last = str(mid).rsplit("/", 1)[-1]
    keys = [_norm(last)]
    if ":" in last:
        keys.append(_norm(last.split(":", 1)[0]))
    return keys


def _price_to_rank(blended):
    """Coarse $/1M (blended in+out) -> a relative `cost` rank on Nikki's scale. Gap-filler
    only: base entries already carry a hand-tuned rank, so this rarely applies."""
    if blended is None:
        return None
    for thresh, rank in ((0.05, 6), (0.5, 7), (1.5, 8), (4, 9), (10, 10)):
        if blended < thresh:
            return rank
    return 11


def sync(catalog_ids, api: dict = None, now_iso: str = None) -> dict:
    """Match each id in `catalog_ids` against models.dev and build the synced facts.
    Returns {synced_at, source, models:{id->facts}, matched:[...], unmatched:[...]}.
    `api` may be passed in (for tests); otherwise it is fetched live."""
    api = api if api is not None else fetch_models_dev()
    idx = build_index(api)
    models, matched, unmatched = {}, [], []
    for mid in catalog_ids:
        facts = next((idx[k] for k in _candidate_keys(mid) if k in idx), None)
        if not facts:
            unmatched.append(mid)
            continue
        entry = {}
        if facts.get("context_window"):
            entry["context_window"] = int(facts["context_window"])
        for f in ("tool_call", "reasoning", "vision"):
            if facts.get(f) is not None:
                entry[f] = bool(facts[f])
        pin, pout = facts.get("price_in"), facts.get("price_out")
        if pin is not None and pout is not None:
            entry["synced_price"] = {"input": pin, "output": pout}
            rank = _price_to_rank((float(pin) + float(pout)) / 2.0)
            if rank is not None:
                entry["cost"] = rank                 # gap-filler only — a base `cost` wins
        if entry:
            models[mid] = entry
            matched.append(mid)
        else:
            unmatched.append(mid)
    stamp = now_iso or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    return {"synced_at": stamp, "source": MODELS_DEV_URL,
            "models": models, "matched": matched, "unmatched": unmatched}


def write_synced(result: dict, path: str = SYNCED_PATH) -> str:
    """Persist the synced facts (the registry loads this file as a gap-fill layer)."""
    payload = {"synced_at": result.get("synced_at"), "source": result.get("source"),
               "models": result.get("models", {})}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=True, allow_unicode=True)
    return path
