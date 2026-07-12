"""
llm.py — the single, provider-agnostic call into any model.

Every model call in the system goes through complete(). Because LiteLLM
normalizes 100+ providers to the OpenAI format, the rest of the code never
knows or cares which provider is behind a model string. This is what makes
models swappable.

Also enforces hard safety limits (the #1 fix from the blueprint review):
no run can exceed its cost cap or iteration cap.
"""
import os
import time
import threading
import contextvars
import concurrent.futures as _futures
from dataclasses import dataclass, field

from dotenv import load_dotenv
load_dotenv()

import litellm

from . import keypool
from . import cache
from . import metrics

# Silently drop params a given provider doesn't support, so the same call
# works across OpenAI / Anthropic / Gemini / local without branching.
litellm.drop_params = True
# Retries are handled by OUR key pool (rotate to another key / cool a bad one) and
# the fallback chain (switch model) — both smarter than litellm retrying the SAME
# key with the SAME api_key. So we disable litellm's own retry to surface a 429
# immediately to the pool. (Letting litellm back off 3x on one key with no timeout
# is exactly what caused a 13-minute cold-start hang.)
litellm.num_retries = 0

# Hard per-call wall-clock timeout (seconds). Bounds a cold-start/stuck provider so
# it fails fast and the fallback chain can move on, instead of freezing the run.
_TIMEOUT = float(os.environ.get("AGENT_LLM_TIMEOUT", "60"))
# How many keys to try for ONE model before giving up on it (then the chain falls
# back to the next model). At least a couple even with a single key (brief backoff).
_KEY_ATTEMPTS = int(os.environ.get("AGENT_KEY_ATTEMPTS", "4"))

# Circuit breaker: once a model fails (timeout / 5xx / rate-limit-exhausted), mark it
# "open" for _BREAKER_COOLDOWN seconds so every later call in the same run (and
# concurrent runs) skips it immediately instead of waiting _TIMEOUT each time.
# This is the fix for multi-minute hangs caused by a dead primary being retried on
# every step. The last model in the chain is NEVER skipped (always a live attempt).
_BREAKER: dict[str, float] = {}        # model_id -> open_until epoch
_BREAKER_FAILS: dict[str, int] = {}    # model_id -> CONSECUTIVE fallbackable failures
_BREAKER_LOCK = threading.Lock()
_BREAKER_COOLDOWN = float(os.environ.get("AGENT_BREAKER_COOLDOWN", "60"))
# Trip the breaker only after this many CONSECUTIVE failures, not the first one. The
# free tier often takes ~_TIMEOUT seconds, so a SINGLE slow call shouldn't sideline a
# model fleet-wide for the whole cooldown (that caused constant fallback churn on tier-3
# runs). Each attempt is still bounded by the wall-clock timeout, so worst case is
# ~threshold×timeout before a genuinely-dead model is benched — the hang protection holds.
_BREAKER_THRESHOLD = max(1, int(os.environ.get("AGENT_BREAKER_THRESHOLD", "2")))
# A rate-limit (429) is a definitive "back off" — unlike a one-off slow timeout, retrying
# in 60s just wastes another slow round-trip. A quota that's exhausted (e.g. Gemini free
# daily) won't recover for many minutes, so bench a rate-limited model for MUCH longer and
# trip on the first hit (no 2-strike wait). This stops every classify/embed/manager call
# from re-probing a dead provider each minute — the biggest latency sink under free-tier 429s.
_BREAKER_RATELIMIT_COOLDOWN = float(os.environ.get("AGENT_RATELIMIT_COOLDOWN", "600"))


def _breaker_open(model: str) -> bool:
    with _BREAKER_LOCK:
        return time.time() < _BREAKER.get(model, 0)


def _record_breaker_failure(model: str) -> bool:
    """Count one consecutive failure; open the breaker once the threshold is reached.
    Returns True if the breaker is now open."""
    with _BREAKER_LOCK:
        n = _BREAKER_FAILS.get(model, 0) + 1
        _BREAKER_FAILS[model] = n
        if n >= _BREAKER_THRESHOLD:
            _BREAKER[model] = time.time() + _BREAKER_COOLDOWN
            return True
        return False


def _trip_breaker(model: str, cooldown: float = None) -> None:
    """Force the breaker open immediately (bypasses the threshold). Optional longer
    cooldown for definitive failures like a rate-limit / quota exhaustion."""
    with _BREAKER_LOCK:
        _BREAKER[model] = time.time() + (cooldown if cooldown is not None else _BREAKER_COOLDOWN)
        _BREAKER_FAILS[model] = _BREAKER_THRESHOLD


def _reset_breaker(model: str) -> None:
    with _BREAKER_LOCK:
        _BREAKER.pop(model, None)
        _BREAKER_FAILS.pop(model, None)


def breaker_status() -> list:
    """Read-only snapshot of the circuit breaker, for the Health dashboard. One row
    per model the breaker is currently tracking (open OR with a non-zero failure
    streak); models that are healthy and untouched are omitted. No secrets."""
    now = time.time()
    out = []
    with _BREAKER_LOCK:
        models = set(_BREAKER) | set(_BREAKER_FAILS)
        for m in models:
            open_until = _BREAKER.get(m, 0)
            remaining = max(0, round(open_until - now))
            fails = _BREAKER_FAILS.get(m, 0)
            if remaining <= 0 and fails <= 0:
                continue
            out.append({"model": m, "open": remaining > 0,
                        "cooldown_s": remaining, "fails": fails,
                        "threshold": _BREAKER_THRESHOLD})
    out.sort(key=lambda r: (not r["open"], -r["cooldown_s"]))
    return out


# Hard wall-clock timeout. litellm's own `timeout=` is NOT reliably enforced for
# every provider (a slow NVIDIA NIM call was observed running ~139s despite
# timeout=45s and returning successfully — so no exception was ever raised and the
# circuit breaker could not trip). We enforce the bound OURSELVES: run the provider
# call on a worker and stop waiting after `timeout`, raising a litellm Timeout the
# fallback chain treats as fallbackable (trips the breaker, advances to the next
# model). The abandoned worker keeps running until the HTTP call returns on its own,
# but the run is no longer blocked. Toggle off with AGENT_HARD_TIMEOUT=0.
_HARD_TIMEOUT = os.environ.get("AGENT_HARD_TIMEOUT", "1").strip().lower() not in ("0", "false", "no")
_LLM_EXEC = _futures.ThreadPoolExecutor(
    max_workers=int(os.environ.get("AGENT_LLM_WORKERS", "16")), thread_name_prefix="llm")


def _timeout_exc(timeout):
    """A litellm.Timeout if this version exposes a constructible one, else a builtin
    TimeoutError. Either is caught as fallbackable by complete_chain."""
    T = getattr(litellm, "Timeout", None)
    if isinstance(T, type):
        try:
            return T(message=f"hard wall-clock timeout after {timeout}s",
                     model="", llm_provider="")
        except Exception:
            try:
                return T(f"hard wall-clock timeout after {timeout}s")
            except Exception:
                pass
    return TimeoutError(f"hard wall-clock timeout after {timeout}s")


def _resolve_timeout(model, timeout):
    """The wall-clock timeout for a model call: an explicit `timeout` wins; else a
    per-model `timeout_s` from the catalog (slow frontier reasoning models get more
    headroom); else the global default. registry is imported LAZILY so llm stays free of
    a registry import cycle (registry/router import llm, never the reverse)."""
    if timeout is not None:
        return timeout
    try:
        from .registry import registry
        t = registry.timeout_for_model(model)
        if t:
            return t
    except Exception:
        pass
    return _TIMEOUT


def _bounded_completion(kwargs):
    """litellm.completion bounded by a hard wall-clock timeout we enforce ourselves."""
    if not _HARD_TIMEOUT:
        return litellm.completion(**kwargs)
    timeout = kwargs.get("timeout") or _TIMEOUT
    fut = _LLM_EXEC.submit(litellm.completion, **kwargs)
    try:
        # Give the worker a small grace beyond litellm's own timeout, so when litellm
        # DOES honor it we surface its richer error rather than our generic one.
        return fut.result(timeout=timeout + 5)
    except _futures.TimeoutError:
        fut.cancel()
        raise _timeout_exc(timeout)


def _iter_stream_bounded(kwargs, timeout=None):
    """Iterate a streaming completion with a hard per-chunk wall-clock bound.

    The same litellm-timeout-not-honored problem applies to streaming: a provider can
    stall before the first token (or mid-stream) with no error raised. The blocking
    provider reads run on a worker thread and are handed back through a queue; if no
    chunk arrives within `timeout`, we abandon and raise a fallbackable Timeout (the
    agent loop then falls back to the bounded non-streaming path). Chunks are YIELDED to
    the calling thread, so on_token/emit side effects stay on the original thread."""
    timeout = timeout or _TIMEOUT
    if not _HARD_TIMEOUT:
        for ch in litellm.completion(**kwargs):
            yield ch
        return
    import queue as _queue
    q: _queue.Queue = _queue.Queue()
    _DONE = object()

    def _producer():
        try:
            for ch in litellm.completion(**kwargs):
                q.put((ch, None))
        except Exception as e:          # surface to the consumer to raise in-thread
            q.put((None, e))
        finally:
            q.put((_DONE, None))

    _LLM_EXEC.submit(_producer)
    while True:
        try:
            item, err = q.get(timeout=timeout + 5)
        except _queue.Empty:
            raise _timeout_exc(timeout)
        if err is not None:
            raise err
        if item is _DONE:
            return
        yield item


def _exc(*names):
    """Build a tuple of litellm exception classes that exist in this version
    (defensive: class names vary slightly across litellm majors)."""
    return tuple(c for c in (getattr(litellm, n, None) for n in names) if isinstance(c, type))


# Rate-limit on one key -> rotate to another key / brief backoff (handled in complete).
_RATE_LIMIT = _exc("RateLimitError")
# A bad/expired key -> bench it and try the next key.
_AUTH = _exc("AuthenticationError")
# Whole MODEL is unhealthy -> the fallback CHAIN should switch models.
_FALLBACKABLE = _exc("RateLimitError", "Timeout", "APITimeoutError", "ServiceUnavailableError",
                     "InternalServerError", "APIConnectionError", "NotFoundError", "APIError")
# A real request/schema bug -> surface it, do NOT silently fall back and hide it.
_BUG = _exc("BadRequestError", "UnsupportedParamsError")


class EmptyResponse(Exception):
    """Provider returned no choices (free-tier throttle / safety filter / empty)."""


class BudgetExceeded(Exception):
    """Raised when a run hits its cost or iteration ceiling."""


@dataclass
class Budget:
    max_usd: float = 1.00          # hard spend cap per run
    # Hard loop cap (prevents runaway agents). Counts EVERY model call in a run —
    # classify + per-subtask dispatch + each agent turn + synthesis — so multi-agent
    # runs need real headroom. The per-agent MAX_TOOL_ROUNDS guard bounds each agent.
    max_iterations: int = 24
    spent_usd: float = 0.0
    iterations: int = 0
    tokens: int = 0          # cumulative LLM tokens used this run (prompt + completion)
    cached_tokens: int = 0   # prompt tokens served from the provider's prompt cache

    def __post_init__(self):
        # Thread-safe: parallel subtasks share one run budget.
        self._lock = threading.Lock()

    def check(self):
        with self._lock:
            if self.spent_usd >= self.max_usd:
                raise BudgetExceeded(
                    # 4 decimals on BOTH figures — a sub-cent cap (e.g. $0.0002) rounded
                    # to 2dp shows a misleading "$0.00".
                    f"cost cap hit: spent ${self.spent_usd:.4f} of ${self.max_usd:.4f}"
                )
            if self.iterations >= self.max_iterations:
                raise BudgetExceeded(f"iteration cap hit: {self.max_iterations}")

    def add_cost(self, usd: float):
        with self._lock:
            self.spent_usd += usd or 0.0

    def add_tokens(self, n: int):
        with self._lock:
            self.tokens += int(n or 0)

    def add_cached_tokens(self, n: int):
        with self._lock:
            self.cached_tokens += int(n or 0)

    def tick(self):
        with self._lock:
            self.iterations += 1

    def child(self, max_usd=None, max_iterations=None):
        """A per-agent sub-budget: enforces its own caps AND the parent's."""
        return _SubBudget(self, max_usd, max_iterations)


class _SubBudget(Budget):
    """Wraps a parent run-budget. Caps this agent locally; every spend/tick also
    counts against the parent, so the global cap is never bypassed."""

    def __init__(self, parent, max_usd=None, max_iterations=None):
        self.parent = parent
        self.max_usd = parent.max_usd if max_usd is None else max_usd
        self.max_iterations = parent.max_iterations if max_iterations is None else max_iterations
        self.spent_usd = 0.0
        self.iterations = 0
        self.tokens = 0
        self.cached_tokens = 0
        self._lock = threading.Lock()

    def check(self):
        self.parent.check()      # global cap first (sequential — no nested locks)
        Budget.check(self)       # then this agent's local cap

    def add_cost(self, usd):
        Budget.add_cost(self, usd)
        self.parent.add_cost(usd)

    def add_tokens(self, n):
        Budget.add_tokens(self, n)
        self.parent.add_tokens(n)

    def add_cached_tokens(self, n):
        Budget.add_cached_tokens(self, n)
        self.parent.add_cached_tokens(n)

    def tick(self):
        Budget.tick(self)
        self.parent.tick()


# The Budget bound to the ACTIVE run, exposed so a model call made from INSIDE a tool
# (e.g. see_image / safety_check / generate_image in tools/) charges the SAME budget as
# the run — preserving the "every model call counts against the run + daily cap"
# invariant even for tool-internal calls. None when no run is active.
_run_budget = contextvars.ContextVar("run_budget", default=None)

# Opaque span context — set by server/trace.py at run start; read by the LLM observer.
# Core holds only the ContextVar; the actual value (e.g. a session_id string) is set
# by server/ so core stays offline. Worker threads re-bind via use_span_ctx.
_span_ctx: contextvars.ContextVar = contextvars.ContextVar("span_ctx", default=None)

# LLM call observer — registered by server/trace.py at startup (default no-op).
# Invoked after each successful complete() with generation metadata so tracing
# can create Langfuse generation spans. Never raises; wraps in try/except below.
_llm_observer = None


def register_llm_observer(fn) -> None:
    """Register a callback invoked after each successful model call.
    Signature: fn(model, cost, prompt_tokens, completion_tokens, latency_ms)."""
    global _llm_observer
    _llm_observer = fn


class use_span_ctx:
    """Re-bind span context in worker threads (mirrors use_budget / using_workspace).
    ThreadPoolExecutor workers don't inherit ContextVars from the submitting thread —
    orchestrator._run_delegation uses this alongside use_budget and using_workspace."""

    def __init__(self, ctx):
        self._ctx = ctx
        self._token = None

    def __enter__(self):
        self._token = _span_ctx.set(self._ctx)
        return self._ctx

    def __exit__(self, *exc):
        if self._token is not None:
            _span_ctx.reset(self._token)
        return False


def current_budget():
    """The Budget bound to the active run (or None outside a run). Tools take a .child()
    of this so their cost rolls up to the run + global daily cap instead of vanishing."""
    return _run_budget.get()


def set_run_budget(budget):
    """Bind `budget` as the active run budget for this context (returns the reset token).
    Called once at the top of a run; a new run rebinds before any model call."""
    return _run_budget.set(budget)


class use_budget:
    """Context manager binding `budget` as the run budget for the block (resets on exit).
    Used to re-establish the budget inside ThreadPoolExecutor worker threads — which do
    NOT inherit the submitting thread's contextvars — so parallel delegations' tool calls
    still charge the run budget."""

    def __init__(self, budget):
        self.budget = budget
        self._token = None

    def __enter__(self):
        self._token = _run_budget.set(self.budget)
        return self.budget

    def __exit__(self, *exc):
        if self._token is not None:
            _run_budget.reset(self._token)
        return False


def _cost_of(resp) -> float:
    try:
        return resp._hidden_params.get("response_cost") or 0.0
    except Exception:
        return 0.0


def _tokens_of(resp) -> int:
    """Total tokens (prompt + completion) from a model response, 0 if unavailable."""
    try:
        u = getattr(resp, "usage", None)
        if u is None:
            return 0
        if isinstance(u, dict):
            return int(u.get("total_tokens") or 0)
        return int(getattr(u, "total_tokens", 0) or 0)
    except Exception:
        return 0


def _prompt_tokens(resp) -> int:
    try:
        u = getattr(resp, "usage", None)
        if u is None:
            return 0
        return int((u.get("prompt_tokens") if isinstance(u, dict)
                    else getattr(u, "prompt_tokens", 0)) or 0)
    except Exception:
        return 0


def _completion_tokens(resp) -> int:
    try:
        u = getattr(resp, "usage", None)
        if u is None:
            return 0
        return int((u.get("completion_tokens") if isinstance(u, dict)
                    else getattr(u, "completion_tokens", 0)) or 0)
    except Exception:
        return 0


def _uget(obj, key):
    """usage sub-objects arrive as dicts OR attribute objects depending on provider."""
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _cached_tokens_of(resp) -> int:
    """Prompt tokens served from the provider's PROMPT CACHE for this call, 0 if none.

    Providers report this differently; we check all shapes LiteLLM passes through:
      * OpenAI-format (normalized): usage.prompt_tokens_details.cached_tokens
      * DeepSeek first-party:       usage.prompt_cache_hit_tokens
      * Anthropic-style:            usage.cache_read_input_tokens
    Cache-hit input is ~50-98% cheaper (DeepSeek: 98% off), so surfacing this is how
    the run summary / dashboard show the REAL savings — counted from provider-reported
    reads, not inferred (the mistake that made OpenCode Go's cost counter wrong)."""
    try:
        u = getattr(resp, "usage", None)
        if u is None:
            return 0
        details = _uget(u, "prompt_tokens_details")
        if details is not None:
            n = _uget(details, "cached_tokens")
            if n:
                return int(n)
        for key in ("prompt_cache_hit_tokens", "cache_read_input_tokens"):
            n = _uget(u, key)
            if n:
                return int(n)
        return 0
    except Exception:
        return 0


def _key_for(model):
    """Acquire one pooled API key value for `model` (None if no pool/keys)."""
    pool = keypool.pool_for_model(model)
    k = pool.acquire() if pool else None
    return k.value if k else None


def _apply_sampling(kwargs: dict, model: str, temperature: float) -> None:
    """Overlay the model's `sampling:` from models.yaml onto call kwargs, in place.

    The model temperature applies ONLY when the caller left the generic default (0.2),
    so an explicit temperature=0 classifier call is preserved. Other knobs (top_p/top_k/
    min_p/repetition_penalty) fill in without clobbering an explicit caller value. Shared
    by complete() AND every streaming path so a model's anti-loop sampling (e.g. Qwen's
    temp 0.55 + repetition_penalty) isn't silently dropped on the streamed build/data path.
    `repeat_penalty` is normalized to `repetition_penalty` (the OpenAI-compatible name that
    vLLM/DeepInfra/NIM actually honor; `repeat_penalty` is the Ollama spelling)."""
    try:
        from .registry import registry as _reg
        samp = _reg.sampling_for(model)
    except Exception:
        samp = {}
    for k, v in (samp or {}).items():
        if k == "repeat_penalty":
            k = "repetition_penalty"
        if k == "temperature":
            if temperature == 0.2:
                kwargs["temperature"] = v
        else:
            kwargs.setdefault(k, v)


def complete(model, messages, tools=None, max_tokens=4096,
             budget: Budget = None, temperature=0.2, timeout=None):
    """
    One call to rule them all. Returns (response, cost_usd).
    `response` is an OpenAI-format ModelResponse regardless of provider.

    Resilience for ONE model (cross-model fallback lives in complete_chain):
      * picks the least-loaded API key from this provider's pool and passes it,
      * on a rate-limit, rotates to another key (or backs off briefly on a single
        key) up to _KEY_ATTEMPTS times,
      * on an auth error, benches that key and tries the next,
      * bounds every call with a wall-clock timeout.
    Raises EmptyResponse on an empty completion so the chain can fall back.
    """
    if budget:
        budget.check()

    kwargs = dict(model=model, messages=messages, max_tokens=max_tokens,
                  temperature=temperature, timeout=_resolve_timeout(model, timeout))
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    _apply_sampling(kwargs, model, temperature)

    pool = keypool.pool_for_model(model)
    last_exc = None
    for attempt in range(_KEY_ATTEMPTS):
        key = pool.acquire() if pool else None
        if key is not None:
            kwargs["api_key"] = key.value
        _t0 = time.time()
        try:
            resp = _bounded_completion(kwargs)
        except _RATE_LIMIT as e:                 # this key is throttled — cool it, rotate
            last_exc = e
            if pool and key:
                pool.penalize(key)
            time.sleep(min(0.3 * (3 ** attempt), 4.0))   # brief backoff (helps single-key)
            continue
        except _AUTH as e:                       # bad/expired key — bench it, try another
            last_exc = e
            if pool and key:
                pool.disable(key)
            continue
        # any other exception propagates (complete_chain decides fall-back vs surface)

        if not getattr(resp, "choices", None):
            raise EmptyResponse(f"{model} returned no choices")
        cost = _cost_of(resp)
        _elapsed = time.time() - _t0
        metrics.record(model, _elapsed, ok=True, cost=cost,
                       prompt_tokens=_prompt_tokens(resp),
                       cached_tokens=_cached_tokens_of(resp))
        if budget:
            budget.add_cost(cost)
            budget.add_tokens(_tokens_of(resp))
            budget.add_cached_tokens(_cached_tokens_of(resp))
            budget.tick()
        if _llm_observer:
            try:
                _llm_observer(model, cost,
                              _prompt_tokens(resp), _completion_tokens(resp),
                              int(_elapsed * 1000))
            except Exception:
                pass
        return resp, cost

    if last_exc:
        raise last_exc
    raise RuntimeError(f"{model}: exhausted key attempts with no response")


def complete_chain(models, messages, tools=None, max_tokens=4096, budget: Budget = None,
                   temperature=0.2, timeout=None, on_fallback=None):
    """
    Try an ORDERED list of models, falling back on failure. Returns (response, cost).

    `models` is the fallback chain (primary first), e.g. from registry.model_chain().
    On a fall-backable failure of one model (all its keys rate-limited / timeout /
    5xx / dead model / empty), move to the NEXT model and call
    `on_fallback(from_model, to_model, reason)` if given (the caller emits a
    `fallback` event). A BudgetExceeded stops everything (a hard cap, never a
    fallback trigger). A genuine request/schema bug (4xx) is surfaced, not hidden.
    """
    chain = [m for m in (models or []) if m]
    if not chain:
        raise ValueError("complete_chain: empty model list")
    last_exc = None
    for i, model in enumerate(chain):
        # Circuit breaker: skip a recently-failed model unless it's the last option.
        # Never skip the last fallback — we always make a live attempt.
        if _breaker_open(model) and i < len(chain) - 1:
            nxt = chain[i + 1]
            # A3: surface breaker-skips in metrics (were invisible before) so the Health
            # dashboard shows how often the breaker is firing.
            metrics.record(model, 0.0, ok=False, fallback=True, error="breaker-skip")
            if on_fallback:
                try:
                    on_fallback(model, nxt, "circuit-breaker: skipped (recent failure)")
                except Exception:
                    pass
            continue
        try:
            resp = complete(model, messages, tools=tools, max_tokens=max_tokens,
                            budget=budget, temperature=temperature, timeout=timeout)
            _reset_breaker(model)             # success — clear failures + any open breaker
            return resp
        except BudgetExceeded:
            raise                                  # hard cap — do not fall back
        except _BUG:
            raise                                  # our bug — surface it, don't mask
        except EmptyResponse as e:
            # A2: a benign empty completion (free-tier throttle / safety filter) is NOT a
            # model-health signal — fall back WITHOUT counting it toward the breaker.
            last_exc = e
            nxt = chain[i + 1] if i + 1 < len(chain) else None
            metrics.record(model, 0.0, ok=False, fallback=bool(nxt), error="EmptyResponse")
            if nxt and on_fallback:
                try:
                    on_fallback(model, nxt, "empty response (not counted against breaker)")
                except Exception:
                    pass
            continue
        except Exception as e:                     # rate-limit-exhausted / timeout / 5xx
            last_exc = e
            if isinstance(e, _RATE_LIMIT):
                # A definitive 429 — bench this model NOW for a long cooldown so later
                # calls skip it fast instead of re-paying the slow round-trip every minute.
                _trip_breaker(model, cooldown=_BREAKER_RATELIMIT_COOLDOWN)
            else:
                # A1: only OPEN the breaker after N consecutive failures, not the first.
                _record_breaker_failure(model)
            nxt = chain[i + 1] if i + 1 < len(chain) else None
            metrics.record(model, 0.0, ok=False, fallback=bool(nxt), error=type(e).__name__)
            if nxt and on_fallback:
                try:
                    on_fallback(model, nxt, f"{type(e).__name__}: {str(e)[:120]}")
                except Exception:
                    pass
            continue
    raise last_exc or RuntimeError("complete_chain: all models failed")


def generate_image(prompt, model, budget: Budget = None, size="1024x1024", n=1):
    """
    Provider-agnostic image generation through the SAME single call point + Budget.
    `model` is a LiteLLM image-model string resolved from config (never hardcoded).
    Returns (response, cost_usd); response.data carries url/b64 per provider.
    Requires the relevant provider key in .env (see PLACEHOLDERS in README).
    """
    if budget:
        budget.check()
    # Use a pooled key (same as text calls) so image gen works with UI-managed /
    # encrypted keys, not only an env var. None when the provider needs no key.
    resp = litellm.image_generation(model=model, prompt=prompt, n=n, size=size,
                                    api_key=_key_for(model))
    cost = 0.0
    try:
        cost = resp._hidden_params.get("response_cost") or 0.0
    except Exception:
        cost = 0.0
    if budget:
        budget.add_cost(cost)
        budget.tick()
    return resp, cost


def stream_complete(model, messages, max_tokens=4096, budget: Budget = None,
                    temperature=0.2, on_token=None):
    """
    Streaming text generation (no tools) through the single call point + Budget.
    Calls `on_token(piece)` for each content delta and returns (full_text, cost).
    Used for the final/synthesized answer so the UI can type it out live.
    """
    if budget:
        budget.check()
    to = _resolve_timeout(model, None)          # honor per-model timeout_s (not the flat default)
    _kw = dict(
        model=model, messages=messages, max_tokens=max_tokens,
        temperature=temperature, stream=True, timeout=to,
        stream_options={"include_usage": True}, api_key=_key_for(model),
    )
    _apply_sampling(_kw, model, temperature)
    _t0 = time.time()
    resp = _iter_stream_bounded(_kw, timeout=to)
    pieces, cost, tokens, ptoks, cached = [], 0.0, 0, 0, 0
    for chunk in resp:
        try:
            piece = chunk.choices[0].delta.content
        except Exception:
            piece = None
        if piece:
            pieces.append(piece)
            if on_token:
                on_token(piece)
        if getattr(chunk, "usage", None):
            try:
                cost = litellm.completion_cost(completion_response=chunk) or cost
            except Exception:
                pass
            tokens = _tokens_of(chunk) or tokens
            ptoks = _prompt_tokens(chunk) or ptoks
            cached = _cached_tokens_of(chunk) or cached
    metrics.record(model, time.time() - _t0, ok=True, cost=cost,
                   prompt_tokens=ptoks, cached_tokens=cached)
    if budget:
        budget.add_cost(cost)
        budget.add_tokens(tokens)
        budget.add_cached_tokens(cached)
        budget.tick()
    return "".join(pieces), cost


def embed(texts, model, budget: Budget = None):
    """Provider-agnostic embeddings through the single call point + Budget.
    Returns (list_of_vectors, cost). Requires an embedding model + provider key.

    Embeddings are deterministic, so results are CACHED per (model, text) — only the
    UNcached texts hit the provider (one call), which makes RAG re-indexing and repeated
    recall near-free on the rate-limited free tier. An all-cached call spends nothing."""
    one = isinstance(texts, str)
    items = [texts] if one else list(texts)
    ec = cache.get_cache("embed", ttl=86400, max_entries=4096)
    keys = [cache.key_for("embed", model, t) for t in items]
    out = [ec.get(k) for k in keys]
    missing = [i for i in range(len(items)) if out[i] is None]
    cost = 0.0
    if missing:
        if budget:
            budget.check()
        resp = litellm.embedding(model=model, input=[items[i] for i in missing],
                                 api_key=_key_for(model))
        try:
            cost = resp._hidden_params.get("response_cost") or 0.0
        except Exception:
            cost = 0.0
        vecs = [(d["embedding"] if isinstance(d, dict) else d.embedding) for d in resp.data]
        for i, v in zip(missing, vecs):
            out[i] = v
            ec.put(keys[i], v)
        if budget:
            budget.add_cost(cost)
            budget.tick()
    return (out[0] if one else out), cost


def stream_complete_tools(model, messages, tools=None, max_tokens=4096,
                          budget: Budget = None, temperature=0.2, on_token=None):
    """
    Streaming WITH tool-calling: streams content deltas via on_token and assembles
    any tool calls from their deltas. Returns (assistant_message_dict, cost) where the
    dict is OpenAI-format ({role, content, tool_calls?}). Building block for per-turn
    streaming (opt-in); the non-streaming complete() remains the default hot path.
    """
    if budget:
        budget.check()
    to = _resolve_timeout(model, None)
    kwargs = dict(model=model, messages=messages, max_tokens=max_tokens,
                  temperature=temperature, stream=True, timeout=to,
                  stream_options={"include_usage": True}, api_key=_key_for(model))
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    _apply_sampling(kwargs, model, temperature)
    # Per-model timeout also bounds the PER-CHUNK watchdog (a slow frontier model may pause
    # between tokens longer than the default; it should fail over only on a true stall).
    _t0 = time.time()
    resp = _iter_stream_bounded(kwargs, timeout=to)

    content, tcs, cost, tokens, ptoks, cached = [], {}, 0.0, 0, 0, 0
    for chunk in resp:
        ch = chunk.choices[0] if getattr(chunk, "choices", None) else None
        delta = getattr(ch, "delta", None) if ch else None
        if delta is not None:
            piece = getattr(delta, "content", None)
            if piece:
                content.append(piece)
                if on_token:
                    on_token(piece)
            for tcd in (getattr(delta, "tool_calls", None) or []):
                idx = getattr(tcd, "index", 0) or 0
                slot = tcs.setdefault(idx, {"id": None, "name": "", "args": ""})
                if getattr(tcd, "id", None):
                    slot["id"] = tcd.id
                fn = getattr(tcd, "function", None)
                if fn:
                    if getattr(fn, "name", None):
                        slot["name"] += fn.name
                    if getattr(fn, "arguments", None):
                        slot["args"] += fn.arguments
        if getattr(chunk, "usage", None):
            try:
                cost = litellm.completion_cost(completion_response=chunk) or cost
            except Exception:
                pass
            tokens = _tokens_of(chunk) or tokens
            ptoks = _prompt_tokens(chunk) or ptoks
            cached = _cached_tokens_of(chunk) or cached

    tool_calls = [
        {"id": s["id"] or f"call_{i}", "type": "function",
         "function": {"name": s["name"], "arguments": s["args"]}}
        for i, s in sorted(tcs.items())
    ]
    msg = {"role": "assistant", "content": "".join(content) or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    metrics.record(model, time.time() - _t0, ok=True, cost=cost,
                   prompt_tokens=ptoks, cached_tokens=cached)
    if budget:
        budget.add_cost(cost)
        budget.add_tokens(tokens)
        budget.add_cached_tokens(cached)
        budget.tick()
    return msg, cost


def stream_complete_chain(models, messages, tools=None, max_tokens=4096,
                          budget: Budget = None, temperature=0.2,
                          on_token=None, on_fallback=None):
    """Streaming variant of complete_chain: tries each model in order, falling back on
    failure. Returns (assistant_message_dict, cost) — same shape as stream_complete_tools.
    on_token(piece) is called for each content delta from the first successful model.
    BudgetExceeded and client-side bugs surface immediately (no fallback)."""
    chain = [m for m in (models or []) if m]
    if not chain:
        raise ValueError("stream_complete_chain: empty model list")
    last_exc = None
    for i, model in enumerate(chain):
        try:
            return stream_complete_tools(model, messages, tools=tools,
                                         max_tokens=max_tokens, budget=budget,
                                         temperature=temperature, on_token=on_token)
        except BudgetExceeded:
            raise
        except _BUG:
            raise
        except Exception as e:
            last_exc = e
            nxt = chain[i + 1] if i + 1 < len(chain) else None
            metrics.record(model, 0.0, ok=False, fallback=bool(nxt), error=type(e).__name__)
            if nxt and on_fallback:
                try:
                    on_fallback(model, nxt, f"{type(e).__name__}: {str(e)[:120]}")
                except Exception:
                    pass
            continue
    raise last_exc or RuntimeError("stream_complete_chain: all models failed")
