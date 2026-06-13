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
from dataclasses import dataclass, field

from dotenv import load_dotenv
load_dotenv()

import litellm

from . import keypool

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
_TIMEOUT = float(os.environ.get("AGENT_LLM_TIMEOUT", "90"))
# How many keys to try for ONE model before giving up on it (then the chain falls
# back to the next model). At least a couple even with a single key (brief backoff).
_KEY_ATTEMPTS = int(os.environ.get("AGENT_KEY_ATTEMPTS", "4"))


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

    def __post_init__(self):
        # Thread-safe: parallel subtasks share one run budget.
        self._lock = threading.Lock()

    def check(self):
        with self._lock:
            if self.spent_usd >= self.max_usd:
                raise BudgetExceeded(
                    f"cost cap hit: spent ${self.spent_usd:.4f} of ${self.max_usd:.2f}"
                )
            if self.iterations >= self.max_iterations:
                raise BudgetExceeded(f"iteration cap hit: {self.max_iterations}")

    def add_cost(self, usd: float):
        with self._lock:
            self.spent_usd += usd or 0.0

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
        self._lock = threading.Lock()

    def check(self):
        self.parent.check()      # global cap first (sequential — no nested locks)
        Budget.check(self)       # then this agent's local cap

    def add_cost(self, usd):
        Budget.add_cost(self, usd)
        self.parent.add_cost(usd)

    def tick(self):
        Budget.tick(self)
        self.parent.tick()


# The Budget bound to the ACTIVE run, exposed so a model call made from INSIDE a tool
# (e.g. see_image / safety_check / generate_image in tools/) charges the SAME budget as
# the run — preserving the "every model call counts against the run + daily cap"
# invariant even for tool-internal calls. None when no run is active.
_run_budget = contextvars.ContextVar("run_budget", default=None)


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


def _key_for(model):
    """Acquire one pooled API key value for `model` (None if no pool/keys)."""
    pool = keypool.pool_for_model(model)
    k = pool.acquire() if pool else None
    return k.value if k else None


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
                  temperature=temperature, timeout=timeout or _TIMEOUT)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    pool = keypool.pool_for_model(model)
    last_exc = None
    for attempt in range(_KEY_ATTEMPTS):
        key = pool.acquire() if pool else None
        if key is not None:
            kwargs["api_key"] = key.value
        try:
            resp = litellm.completion(**kwargs)
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
        if budget:
            budget.add_cost(cost)
            budget.tick()
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
        try:
            return complete(model, messages, tools=tools, max_tokens=max_tokens,
                            budget=budget, temperature=temperature, timeout=timeout)
        except BudgetExceeded:
            raise                                  # hard cap — do not fall back
        except _BUG:
            raise                                  # our bug — surface it, don't mask
        except Exception as e:                     # rate-limit-exhausted / timeout / 5xx / empty
            last_exc = e
            nxt = chain[i + 1] if i + 1 < len(chain) else None
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
    resp = litellm.image_generation(model=model, prompt=prompt, n=n, size=size)
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
    resp = litellm.completion(
        model=model, messages=messages, max_tokens=max_tokens,
        temperature=temperature, stream=True, timeout=_TIMEOUT,
        stream_options={"include_usage": True}, api_key=_key_for(model),
    )
    pieces, cost = [], 0.0
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
    if budget:
        budget.add_cost(cost)
        budget.tick()
    return "".join(pieces), cost


def embed(texts, model, budget: Budget = None):
    """Provider-agnostic embeddings through the single call point + Budget.
    Returns (list_of_vectors, cost). Requires an embedding model + provider key."""
    one = isinstance(texts, str)
    if budget:
        budget.check()
    resp = litellm.embedding(model=model, input=[texts] if one else list(texts),
                             api_key=_key_for(model))
    cost = 0.0
    try:
        cost = resp._hidden_params.get("response_cost") or 0.0
    except Exception:
        cost = 0.0
    if budget:
        budget.add_cost(cost)
        budget.tick()
    vecs = [(d["embedding"] if isinstance(d, dict) else d.embedding) for d in resp.data]
    return (vecs[0] if one else vecs), cost


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
    kwargs = dict(model=model, messages=messages, max_tokens=max_tokens,
                  temperature=temperature, stream=True, timeout=_TIMEOUT,
                  stream_options={"include_usage": True}, api_key=_key_for(model))
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    resp = litellm.completion(**kwargs)

    content, tcs, cost = [], {}, 0.0
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

    tool_calls = [
        {"id": s["id"] or f"call_{i}", "type": "function",
         "function": {"name": s["name"], "arguments": s["args"]}}
        for i, s in sorted(tcs.items())
    ]
    msg = {"role": "assistant", "content": "".join(content) or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if budget:
        budget.add_cost(cost)
        budget.tick()
    return msg, cost
