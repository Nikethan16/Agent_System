"""
metrics.py — lightweight per-LLM-call metrics for the Model Health view (offline).

Records a bounded ring buffer of recent model calls plus running per-model aggregates
(calls, errors, fallbacks, average latency, cost). This is the CALL-level signal the
event-level trace (server/trace.py) lacked — it answers "which models are slow / erroring
/ getting fallen-back-from?", which is exactly what the multi-key NVIDIA fleet needs to
tune. Stdlib only; stays in core (no provider deps beyond reading the model string).
"""
import os
import json
import time
import atexit
import threading
from collections import deque, defaultdict

from .keypool import provider_of

_MAX = int(os.environ.get("AGENT_METRICS_MAX", "500"))
_lock = threading.Lock()
_recent = deque(maxlen=_MAX)


def _blank():
    return {"calls": 0, "errors": 0, "fallbacks": 0, "latency_sum": 0.0,
            "latency_n": 0, "cost": 0.0, "prompt_tokens": 0, "cached_tokens": 0}


_agg = defaultdict(_blank)


def record(model: str, latency: float, ok: bool = True, cost: float = 0.0,
           fallback: bool = False, error: str = None,
           prompt_tokens: int = 0, cached_tokens: int = 0) -> None:
    """Record one model-call outcome. Never raises (telemetry must not break a run)."""
    try:
        rec = {"ts": time.time(), "model": model, "provider": provider_of(model),
               "latency": round(latency or 0.0, 3), "ok": bool(ok),
               "cost": round(cost or 0.0, 6), "fallback": bool(fallback), "error": error,
               "cached_tokens": int(cached_tokens or 0)}
        with _lock:
            _recent.append(rec)
            a = _agg[model]
            a["calls"] += 1
            if not ok:
                a["errors"] += 1
            if fallback:
                a["fallbacks"] += 1
            if ok and latency:
                a["latency_sum"] += latency
                a["latency_n"] += 1
            a["cost"] += cost or 0.0
            a["prompt_tokens"] += int(prompt_tokens or 0)
            a["cached_tokens"] += int(cached_tokens or 0)
        _maybe_persist()
    except Exception:
        pass


# ---- reliability / health scoring + persistence --------------------------------
_MIN_SAMPLE = int(os.environ.get("AGENT_HEALTH_MIN_SAMPLE", "4"))
_BAD_RATE = float(os.environ.get("AGENT_HEALTH_BAD_RATE", "0.5"))
_WINDOW = int(os.environ.get("AGENT_HEALTH_WINDOW", "30"))
_STORE = os.path.join(os.environ.get("DATA_DIR", "data"), "model_health.json")
_SAVE_EVERY = int(os.environ.get("AGENT_HEALTH_SAVE_EVERY", "25"))
_since_save = 0


def reliability(model: str) -> float:
    """Rolling reliability in [0,1] from the RECENT-call window (self-correcting — no stale
    forever-penalty). Returns 1.0 when there's too little data (unknown -> benefit of the
    doubt), so routing behaves exactly as before until a model actually proves flaky."""
    with _lock:
        calls = [r for r in _recent if r.get("model") == model][-_WINDOW:]
    if len(calls) < _MIN_SAMPLE:
        return 1.0
    errs = sum(1 for r in calls if not r.get("ok"))
    return max(0.0, 1.0 - errs / len(calls))


def is_degraded(model: str) -> bool:
    """True when a model has enough recent samples AND a high error rate — the picker should
    prefer a healthier capable model. Unknown/low-data models are never degraded."""
    return reliability(model) < (1.0 - _BAD_RATE)


def _persist() -> None:
    """Best-effort save so the health signal survives restarts (telemetry, never raises)."""
    try:
        with _lock:
            data = {"recent": list(_recent), "agg": {k: dict(v) for k, v in _agg.items()}}
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        tmp = _STORE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, _STORE)
    except Exception:
        pass


def _maybe_persist() -> None:
    global _since_save
    _since_save += 1
    if _since_save >= _SAVE_EVERY:
        _since_save = 0
        _persist()


def _load_persisted() -> None:
    try:
        with open(_STORE, encoding="utf-8") as f:
            data = json.load(f)
        with _lock:
            for r in (data.get("recent") or []):
                _recent.append(r)
            for k, v in (data.get("agg") or {}).items():
                a = _agg[k]
                for kk, vv in v.items():
                    a[kk] = vv
    except Exception:
        pass


def recent(n: int = 100) -> list:
    with _lock:
        items = list(_recent)
    return items[-n:][::-1]          # newest first


def summary() -> list:
    """Per-model rollup, busiest first — for the Model Health dashboard."""
    with _lock:
        rows = []
        for model, a in _agg.items():
            n = a["latency_n"]
            pt = a["prompt_tokens"]
            rows.append({
                "model": model, "provider": provider_of(model),
                "calls": a["calls"], "errors": a["errors"],
                "error_rate": round(a["errors"] / a["calls"], 3) if a["calls"] else 0.0,
                "fallbacks": a["fallbacks"],
                "avg_latency": round(a["latency_sum"] / n, 3) if n else None,
                "cost": round(a["cost"], 6),
                # Prompt-cache effectiveness: what share of prompt tokens the provider
                # served from cache (cache-hit input is ~50-98% cheaper). None until
                # the provider reports token details.
                "cached_tokens": a["cached_tokens"],
                "cache_hit_rate": round(a["cached_tokens"] / pt, 3) if pt else None,
            })
    rows.sort(key=lambda r: -r["calls"])
    return rows


def reset() -> None:
    with _lock:
        _recent.clear()
        _agg.clear()


# Warm-start reliability from the persisted signal (best-effort) + save on process exit,
# so model health survives restarts instead of resetting to "unknown" every boot.
_load_persisted()
atexit.register(_persist)
