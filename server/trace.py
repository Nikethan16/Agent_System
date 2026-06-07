"""
trace.py — observability (roadmap #5).

Writes a structured, append-only trace of every run event to data/traces/<session>.jsonl
(always on, offline). If Langfuse keys are present in .env it ALSO forwards spans to
Langfuse. The append-only tool/gate audit log (core/policy.py) complements this.

Langfuse forwarding is resilient across SDK majors:
  * v2 SDK  — uses `client.trace(...)` + `trace.event(...)`
  * v3 SDK  — OpenTelemetry-based; uses `client.create_event(...)` (falls back to
              `start_span(...).end()` if `create_event` is absent)
Events are batched by the SDK, so we register a `flush()` at interpreter exit and the
FastAPI app calls it on shutdown — without a flush, short-lived processes drop events.
Everything is wrapped so telemetry can NEVER break a real run. See docs/PLACEHOLDERS.md
(row 5): set LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY and `pip install langfuse`.
"""
import os
import json
import time
import atexit
import threading

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "traces")
os.makedirs(_DIR, exist_ok=True)
_lock = threading.Lock()

_LANGFUSE = bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))
_lf_client = None
_lf_unavailable = False        # set True once if the SDK can't be initialised, to stop retrying
_lf_major = None               # detected SDK major version (2 or 3)
_lf_traces: dict = {}
_LF_TRACE_CACHE_MAX = 512      # cap the per-session Langfuse trace cache


def trace(session_id: str, event: dict) -> None:
    rec = {"ts": time.time(), "session_id": session_id, **event}
    path = os.path.join(_DIR, f"{session_id}.jsonl")
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    if _LANGFUSE and not _lf_unavailable:
        _forward_langfuse(rec)


def _ensure_client():
    """Lazily build the Langfuse client and detect its major version. Returns the
    client or None (and latches _lf_unavailable on hard failure so we stop retrying)."""
    global _lf_client, _lf_major, _lf_unavailable
    if _lf_client is not None or _lf_unavailable:
        return _lf_client
    try:
        import langfuse as _lf_mod
        from langfuse import Langfuse            # reads LANGFUSE_* from env
        ver = getattr(_lf_mod, "__version__", "") or ""
        try:
            _lf_major = int(ver.split(".")[0]) if ver else None
        except (ValueError, IndexError):
            _lf_major = None
        _lf_client = Langfuse()
        return _lf_client
    except Exception:
        _lf_unavailable = True                   # missing SDK / bad creds — don't retry every event
        return None


def _forward_langfuse(rec: dict) -> None:
    """Forward one event to Langfuse, resilient to SDK v2/v3 API differences."""
    try:
        client = _ensure_client()
        if client is None:
            return
        sid = rec.get("session_id")
        name = str(rec.get("type", "event"))
        meta = {k: v for k, v in rec.items() if k not in ("ts", "session_id")}

        # --- v3 (OTEL) path: prefer flat events on a shared trace context ----
        if _lf_major == 3 or not hasattr(client, "trace"):
            if hasattr(client, "create_event"):
                client.create_event(name=name, metadata=meta)
            elif hasattr(client, "start_span"):
                span = client.start_span(name=name, metadata=meta)
                end = getattr(span, "end", None)
                if callable(end):
                    end()
            return

        # --- v2 path: one trace per session, events attached to it -----------
        with _lock:                                  # _lf_traces is shared across threads
            tr = _lf_traces.get(sid)
            if tr is None:
                tr = client.trace(name="agent-run", session_id=sid)
                if len(_lf_traces) >= _LF_TRACE_CACHE_MAX:
                    _lf_traces.pop(next(iter(_lf_traces)), None)   # evict oldest
                _lf_traces[sid] = tr
        tr.event(name=name, metadata=meta)
    except Exception:
        pass  # never let observability break the actual run


def flush() -> None:
    """Flush buffered Langfuse events. Safe to call anytime (no-op without Langfuse).
    Registered at interpreter exit and invoked by the FastAPI app on shutdown so
    short-lived processes don't drop their final spans."""
    client = _lf_client
    if client is None:
        return
    try:
        fn = getattr(client, "flush", None)
        if callable(fn):
            fn()
    except Exception:
        pass


# Best-effort flush when the process exits (covers scripts + the dev server).
atexit.register(flush)
