"""
metrics.py — lightweight per-LLM-call metrics for the Model Health view (offline).

Records a bounded ring buffer of recent model calls plus running per-model aggregates
(calls, errors, fallbacks, average latency, cost). This is the CALL-level signal the
event-level trace (server/trace.py) lacked — it answers "which models are slow / erroring
/ getting fallen-back-from?", which is exactly what the multi-key NVIDIA fleet needs to
tune. Stdlib only; stays in core (no provider deps beyond reading the model string).
"""
import os
import time
import threading
from collections import deque, defaultdict

from .keypool import provider_of

_MAX = int(os.environ.get("AGENT_METRICS_MAX", "500"))
_lock = threading.Lock()
_recent = deque(maxlen=_MAX)


def _blank():
    return {"calls": 0, "errors": 0, "fallbacks": 0, "latency_sum": 0.0,
            "latency_n": 0, "cost": 0.0}


_agg = defaultdict(_blank)


def record(model: str, latency: float, ok: bool = True, cost: float = 0.0,
           fallback: bool = False, error: str = None) -> None:
    """Record one model-call outcome. Never raises (telemetry must not break a run)."""
    try:
        rec = {"ts": time.time(), "model": model, "provider": provider_of(model),
               "latency": round(latency or 0.0, 3), "ok": bool(ok),
               "cost": round(cost or 0.0, 6), "fallback": bool(fallback), "error": error}
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
            rows.append({
                "model": model, "provider": provider_of(model),
                "calls": a["calls"], "errors": a["errors"],
                "error_rate": round(a["errors"] / a["calls"], 3) if a["calls"] else 0.0,
                "fallbacks": a["fallbacks"],
                "avg_latency": round(a["latency_sum"] / n, 3) if n else None,
                "cost": round(a["cost"], 6),
            })
    rows.sort(key=lambda r: -r["calls"])
    return rows


def reset() -> None:
    with _lock:
        _recent.clear()
        _agg.clear()
