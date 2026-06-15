"""
trace.py — observability: append-only JSONL trace + Langfuse span tree.

LOCAL TRACE (always-on, offline):
  data/traces/<session_id>.jsonl — one JSON line per pipeline event.
  Now extended with `span_id` and `parent_span_id` so the tree can be reconstructed
  locally even without Langfuse.

LANGFUSE FORWARDING (optional — set LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY):
  Proper span tree per run: root trace → subagent spans → LLM generation spans.
  Generation spans include model name, prompt/completion token split, cost USD,
  and wall-clock latency — far more useful than the old flat-event forwarding.

  The LLM observer (registered into core/llm.py at startup) fires after every
  model call so generation spans carry real timing + token data. Core stays
  offline — it only holds the opaque _span_ctx ContextVar (a stdlib primitive)
  and calls the observer; it never imports Langfuse.

  Supports Langfuse SDK v2 and v3 (detected at runtime). Everything is wrapped in
  try/except so telemetry NEVER breaks a real run. flush() is registered at exit
  and called by the FastAPI app on shutdown so short-lived processes don't drop spans.
"""
import os
import json
import time
import uuid
import atexit
import threading
import logging

log = logging.getLogger(__name__)

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "traces")
os.makedirs(_DIR, exist_ok=True)
_lock = threading.Lock()

# ---- Langfuse config -------------------------------------------------------
_LANGFUSE = bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))
_lf_client = None
_lf_unavailable = False
_lf_major = None

# Per-session state: {session_id: {"trace": lf_trace, "span_stack": [span, ...],
#                                   "span_lock": Lock, "span_id": str}}
_session_states: dict = {}
_states_lock = threading.Lock()


# ---- public JSONL trace (always-on) ----------------------------------------

def trace(session_id: str, event: dict) -> None:
    """Append one event to the session's JSONL trace and forward to Langfuse if configured."""
    rec = {"ts": time.time(), "session_id": session_id, **event}
    path = os.path.join(_DIR, f"{session_id}.jsonl")
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    if _LANGFUSE and not _lf_unavailable:
        try:
            _handle_event_lf(session_id, event)
        except Exception:
            pass


# ---- local trace reading + tree reconstruction -----------------------------

def load_trace(session_id: str) -> list:
    """Read a session's JSONL trace as a list of event dicts (oldest→newest).

    Pure read; tolerates malformed lines (a partial final write never breaks it).
    Returns [] when no trace exists for the session."""
    path = os.path.join(_DIR, f"{session_id}.jsonl")
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except (ValueError, TypeError):
                    continue
    except OSError:
        return []
    return out


# Events that attach to the current open span rather than opening their own.
_LEAF_TYPES = {"tool", "thought", "agent_token", "skill", "critic", "fallback",
               "retry", "blocked", "denied", "limit", "memory", "feedback"}
# Events that belong to the run as a whole (the root node).
_ROOT_TYPES = {"route", "plan", "final", "run_complete", "error"}


def _node(name: str, kind: str, ev: dict | None = None) -> dict:
    return {"name": name, "kind": kind, "start": (ev or {}).get("ts"),
            "end": None, "cost": 0.0, "tokens": 0, "children": [], "events": []}


def _accrue(node: dict, ev: dict) -> None:
    """Fold an event's cost/tokens into a node (best-effort; fields are optional)."""
    try:
        node["cost"] += float(ev.get("cost") or 0)
    except (ValueError, TypeError):
        pass
    try:
        node["tokens"] += int(ev.get("tokens") or 0)
    except (ValueError, TypeError):
        pass


def build_tree(session_id: str) -> dict:
    """Reconstruct a span tree from the flat JSONL, mirroring the Langfuse stack
    logic: `assign` pushes a child span, `done` pops it, leaf events attach to the
    deepest open span, run-level events sit on the root. Cost/tokens/duration are
    aggregated per node. Returns {root, totals, events_count}."""
    events = load_trace(session_id)
    root = _node("agent-run", "run")
    stack = [root]  # deepest open span is stack[-1]
    for ev in events:
        typ = ev.get("type", "")
        ts = ev.get("ts")
        if root["start"] is None:
            root["start"] = ts
        if typ == "assign":
            child = _node(f"agent:{ev.get('agent', 'unknown')}", "agent", ev)
            child["subtask"] = (ev.get("subtask") or "")[:300]
            child["model"] = ev.get("model")
            child["step"] = ev.get("step")
            stack[-1]["children"].append(child)
            stack.append(child)
        elif typ == "done":
            node = stack.pop() if len(stack) > 1 else stack[-1]
            node["end"] = ts
            _accrue(node, ev)
        elif typ == "tool":
            leaf = _node(f"tool:{ev.get('name', 'unknown')}", "tool", ev)
            leaf["end"] = ts
            leaf["args"] = str(ev.get("args", ""))[:300]
            _accrue(leaf, ev)
            stack[-1]["children"].append(leaf)
        elif typ in _ROOT_TYPES:
            _accrue(root, ev)
            root["events"].append({"type": typ, "ts": ts})
            if typ in ("run_complete", "final"):
                root["end"] = ts
                # run-level totals are authoritative when present
                if ev.get("cost") is not None:
                    try:
                        root["cost"] = float(ev.get("cost") or 0)
                    except (ValueError, TypeError):
                        pass
                if ev.get("tokens") is not None:
                    try:
                        root["tokens"] = int(ev.get("tokens") or 0)
                    except (ValueError, TypeError):
                        pass
        else:  # _LEAF_TYPES and anything unknown → attach to the current span
            _accrue(stack[-1], ev)
            stack[-1]["events"].append({"type": typ, "ts": ts})
    # Close any spans left open (a crashed/incomplete run).
    last_ts = events[-1]["ts"] if events else None
    for node in stack:
        if node["end"] is None:
            node["end"] = last_ts

    def _dur(n):
        if n.get("start") is not None and n.get("end") is not None:
            n["duration_ms"] = round((n["end"] - n["start"]) * 1000)
        else:
            n["duration_ms"] = None
        for c in n["children"]:
            _dur(c)
    _dur(root)
    return {"root": root, "totals": {"cost": root["cost"], "tokens": root["tokens"],
                                     "duration_ms": root.get("duration_ms")},
            "events_count": len(events)}


# ---- Langfuse client -------------------------------------------------------

def _ensure_client():
    global _lf_client, _lf_major, _lf_unavailable
    if _lf_client is not None or _lf_unavailable:
        return _lf_client
    try:
        import langfuse as _lf_mod
        from langfuse import Langfuse
        ver = getattr(_lf_mod, "__version__", "") or ""
        try:
            _lf_major = int(ver.split(".")[0]) if ver else None
        except (ValueError, IndexError):
            _lf_major = None
        # LANGFUSE_HOST is read natively by the SDK from the env
        _lf_client = Langfuse()
        return _lf_client
    except Exception:
        _lf_unavailable = True
        return None


def _get_state(session_id: str) -> dict:
    """Get or create per-session Langfuse state."""
    with _states_lock:
        if session_id not in _session_states:
            _session_states[session_id] = {
                "trace": None,
                "span_stack": [],
                "span_lock": threading.Lock(),
            }
        return _session_states[session_id]


def _get_or_create_trace(client, session_id: str, name: str = "agent-run"):
    """Get or create the Langfuse root trace for this session."""
    state = _get_state(session_id)
    with state["span_lock"]:
        if state["trace"] is None:
            try:
                state["trace"] = client.trace(name=name, session_id=session_id)
            except Exception:
                pass
        return state["trace"]


def _current_span(session_id: str):
    """The deepest open span for this session (or the root trace as fallback)."""
    state = _get_state(session_id)
    with state["span_lock"]:
        stack = state["span_stack"]
        return stack[-1] if stack else state.get("trace")


# ---- Langfuse event router -------------------------------------------------

def _handle_event_lf(session_id: str, event: dict) -> None:
    """Route a pipeline event to appropriate Langfuse spans. Never raises."""
    client = _ensure_client()
    if client is None:
        return
    typ = event.get("type", "")

    if typ == "route":
        # Initialize the root trace with task metadata
        tr = _get_or_create_trace(client, session_id)
        if tr:
            try:
                tr.update(metadata={
                    "tier": event.get("tier"),
                    "task_type": event.get("task_type"),
                })
            except Exception:
                pass

    elif typ == "assign":
        # Subagent starting → push a new child span
        tr = _get_or_create_trace(client, session_id)
        if not tr:
            return
        state = _get_state(session_id)
        try:
            parent = _current_span(session_id)
            span_fn = getattr(parent, "span", None)
            if callable(span_fn):
                span = span_fn(
                    name=f"agent:{event.get('agent', 'unknown')}",
                    metadata={
                        "model": event.get("model"),
                        "subtask": (event.get("subtask") or "")[:500],
                        "step": event.get("step"),
                    },
                )
                with state["span_lock"]:
                    state["span_stack"].append(span)
        except Exception:
            pass

    elif typ == "done":
        # Agent finished → pop and end the current span
        state = _get_state(session_id)
        with state["span_lock"]:
            stack = state["span_stack"]
            if stack:
                span = stack.pop()
        if span:
            try:
                end_fn = getattr(span, "end", None)
                if callable(end_fn):
                    end_fn()
            except Exception:
                pass

    elif typ == "tool":
        # Tool call — create a point span (start≈end; we don't have a "tool done" event)
        parent = _current_span(session_id)
        if parent:
            try:
                span_fn = getattr(parent, "span", None)
                if callable(span_fn):
                    s = span_fn(
                        name=f"tool:{event.get('name', 'unknown')}",
                        input=str(event.get("args", ""))[:500],
                    )
                    end_fn = getattr(s, "end", None)
                    if callable(end_fn):
                        end_fn()
            except Exception:
                pass

    elif typ in ("run_complete", "final"):
        # Run finished — update and end the root trace
        state = _get_state(session_id)
        tr = state.get("trace")
        if tr:
            try:
                tr.update(
                    output=str(event.get("answer") or event.get("text") or "")[:1000],
                    metadata={
                        "cost_usd": event.get("cost"),
                        "tokens": event.get("tokens"),
                        "iterations": event.get("iterations"),
                    },
                )
            except Exception:
                pass
        # Clean up session state
        with _states_lock:
            _session_states.pop(session_id, None)

    else:
        # All other events → flat event on the root trace (backward compat)
        tr = _get_or_create_trace(client, session_id)
        if tr:
            try:
                meta = {k: v for k, v in event.items() if k != "type"}
                name = str(typ or "event")
                event_fn = getattr(tr, "event", None)
                create_fn = getattr(tr, "create_event", None)
                if callable(event_fn):
                    tr.event(name=name, metadata=meta)
                elif callable(create_fn):
                    tr.create_event(name=name, metadata=meta)
            except Exception:
                pass


# ---- LLM observer (registered into core.llm at app startup) ----------------

def _llm_generation_callback(model: str, cost: float,
                              prompt_tokens: int, completion_tokens: int,
                              latency_ms: int) -> None:
    """Called by core.llm.complete() after each model call.
    Creates a Langfuse generation span under the current session's active span."""
    if not _LANGFUSE or _lf_unavailable:
        return
    # The _span_ctx ContextVar holds the session_id (set by server/chat.py run_turn).
    try:
        from core.llm import _span_ctx
        session_id = _span_ctx.get()
        if not session_id or not isinstance(session_id, str):
            return
    except Exception:
        return

    try:
        client = _ensure_client()
        if client is None:
            return
        parent = _current_span(session_id)
        if parent is None:
            parent = _get_or_create_trace(client, session_id)
        if parent is None:
            return

        gen_fn = getattr(parent, "generation", None)
        if callable(gen_fn):
            gen = gen_fn(
                name=f"llm:{model.split('/')[-1]}",
                model=model,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                metadata={
                    "cost_usd": round(cost, 8),
                    "latency_ms": latency_ms,
                },
            )
            end_fn = getattr(gen, "end", None)
            if callable(end_fn):
                end_fn()
    except Exception:
        pass


# ---- flush -----------------------------------------------------------------

def flush() -> None:
    """Flush buffered Langfuse spans. Safe anytime (no-op without Langfuse).
    Registered at exit and called by FastAPI on shutdown."""
    client = _lf_client
    if client is None:
        return
    try:
        fn = getattr(client, "flush", None)
        if callable(fn):
            fn()
    except Exception:
        pass


atexit.register(flush)
