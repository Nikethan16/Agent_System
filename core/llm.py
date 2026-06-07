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
import threading
from dataclasses import dataclass, field

from dotenv import load_dotenv
load_dotenv()

import litellm
# Silently drop params a given provider doesn't support, so the same call
# works across OpenAI / Anthropic / Gemini / local without branching.
litellm.drop_params = True
# Free tiers (NVIDIA NIM, Gemini free, OpenRouter :free) rate-limit aggressively.
# Retry transient errors (429 / timeouts) with exponential backoff so a single
# rate-limit blip doesn't fail the whole run.
litellm.num_retries = 3


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


def complete(model, messages, tools=None, max_tokens=4096,
             budget: Budget = None, temperature=0.2):
    """
    One call to rule them all. Returns (response, cost_usd).
    `response` is an OpenAI-format ModelResponse regardless of provider.
    """
    if budget:
        budget.check()

    kwargs = dict(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    resp = litellm.completion(**kwargs)

    # LiteLLM attaches the computed cost here for supported models.
    cost = 0.0
    try:
        cost = resp._hidden_params.get("response_cost") or 0.0
    except Exception:
        cost = 0.0

    if budget:
        budget.add_cost(cost)
        budget.tick()

    return resp, cost


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
        temperature=temperature, stream=True,
        stream_options={"include_usage": True},
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
    resp = litellm.embedding(model=model, input=[texts] if one else list(texts))
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
                  temperature=temperature, stream=True,
                  stream_options={"include_usage": True})
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
