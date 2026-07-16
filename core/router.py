"""
router.py — the brain. A cheap classifier call that decides how hard a task is.

Routing cost is near-zero because it uses the tier1 (cheapest) model. Robustness:
  * transient/rate-limit errors get ONE short backoff-retry before giving up,
  * a real BudgetExceeded is re-raised (never silently swallowed),
  * if classification still fails we fall back DOWN to tier 1 (a single cheap,
    tool-less-friendly path) — NOT up to a tool-heavy tier. A failed route must
    never be able to escalate a trivial message into a tool-spin.
"""
import json
import re
import time

from .llm import complete_chain, Budget, BudgetExceeded
from .registry import registry

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def _extract_route_json(txt: str) -> dict:
    """Pull the routing JSON out of a model reply that may include reasoning traces,
    prose, or code fences. The old naive first-'{' .. last-'}' span broke when a
    reasoning model emitted text CONTAINING braces before the JSON (observed live:
    JSONDecodeError -> heuristic fallback every route). Strategy: strip <think> blocks
    and fences, then try each BALANCED {...} candidate (last first — the JSON trails the
    reasoning), returning the first that parses and has a 'tier' key."""
    if not txt:
        raise ValueError("empty classifier reply")
    s = _THINK.sub("", txt).replace("```json", "").replace("```", "")
    candidates, stack, start = [], [], None
    for i, ch in enumerate(s):
        if ch == "{":
            if not stack:
                start = i
            stack.append(ch)
        elif ch == "}" and stack:
            stack.pop()
            if not stack and start is not None:
                candidates.append(s[start:i + 1])
    for cand in reversed(candidates):          # JSON usually comes AFTER any reasoning
        try:
            d = json.loads(cand)
            if isinstance(d, dict) and "tier" in d:
                return d
        except Exception:
            continue
    return json.loads(s[s.find("{"): s.rfind("}") + 1])   # last-resort naive span

CLASSIFIER_SYS = (
    "You are a task router. Output ONLY valid JSON, no prose, no code fences:\n"
    '{"tier": 1|2|3, "task_type": '
    '"chat"|"general"|"coding"|"writing"|"research"|"math"|"data", '
    '"requires_web": true|false, "reason": "<=8 words"}\n\n'
    "TASK_TYPE RULES — pick the one that fits; do NOT force a Q&A into 'coding':\n"
    "  chat     — greetings, small talk, thanks.\n"
    "  general  — a plain question / explanation / factual lookup / opinion where the answer "
    "is just TEXT and NO file, code, or document is produced (e.g. 'what is the capital of "
    "France?', 'explain how caching works'). This is the default for questions.\n"
    "  coding   — ONLY when NEW code/scripts/tests must be written or run.\n"
    "  writing  — producing a document/essay/email/report as a deliverable.\n"
    "  research — needs looking things up online / current info / multiple sources.\n"
    "  math     — a calculation/proof.   data — analyzing a dataset/CSV.\n\n"
    "TIER RULES — bias toward tier 1 for pure Q&A, tier 2 for real build/write work:\n"
    "Tier 1 — trivial: greeting, a single factual/explanatory question, format/classify/"
    "summarize a snippet. Most 'chat' and 'general' tasks are tier 1.\n"
    "Tier 2 — DEFAULT for real work: writing ONE file or script, ONE component, ONE focused "
    "feature, fixing a bug, building an app that fits in a single session (a calculator, "
    "landing page, form, CLI tool, etc.), drafting a document, analyzing data. A single "
    "specialist handles this in one loop — no planner, no delegation needed.\n"
    "Tier 3 — RARE. Only genuinely multi-component systems whose independent parts MUST be "
    "built and coordinated separately (full-stack app with backend + DB + frontend + tests "
    "as separate deliverables, multi-step research needing 3+ distinct sources). Do NOT use "
    "tier 3 for anything one skilled engineer can finish in one session.\n\n"
    "Examples: 'hi' → tier 1 chat. 'what is the capital of France?' → tier 1 general. "
    "'explain why AI routes tasks into tiers' → tier 1 general. 'build a calculator' → tier 2 "
    "coding. 'write a blog post about X' → tier 2 writing. 'build a REST API with auth, "
    "PostgreSQL, tests, and React frontend' → tier 3 coding."
)

_RETRIES = 1          # extra attempts after the first, on transient/rate-limit errors
_BACKOFF_SECONDS = 2.0

# B1: cache routing verdicts keyed on the USER'S request (not the assembled context,
# which changes every turn). Saves the classifier call on repeated/identical asks +
# retries. Bounded (simple FIFO eviction); `routed_model` is recomputed on a hit so a
# model swap is still reflected.
_CACHE = {}
_CACHE_MAX = 256


def _cache_key(task: str) -> str:
    marker = "NEW REQUEST:"
    i = (task or "").rfind(marker)
    return (task[i + len(marker):] if i != -1 else task).strip()[:500]


def _is_transient(err: Exception) -> bool:
    name = type(err).__name__.lower()
    text = str(err).lower()
    return ("ratelimit" in name or "timeout" in name or "serviceunavailable" in name
            or "rate limit" in text or "429" in text or "503" in text or "overloaded" in text)


# Keyword heuristic used ONLY when the LLM classifier fails (transient error / empty
# response). Previously every failure routed to tier-1/"unknown", which mis-sent real
# coding builds to a trivial single-shot path (observed 2026-06-22: the same build prompt
# classified tier-3 once and tier-1/unknown once). The heuristic picks a sane tier+type
# from the text instead — but NEVER above tier 2 (a single specialist, no planner), so the
# original guarantee that a failed route can't escalate a message into tool-heavy work holds.
_CODING_HINTS = ("code", "function", "class ", "implement", "build a", "build an", "script",
                 "api", "endpoint", "pytest", "unit test", "compiler", "parser", "lexer",
                 "cli", "refactor", "debug", "fix the", "python", "javascript", "typescript",
                 "react", "fastapi", "flask", ".py", ".js", ".ts", "html", "css", "sql")
_RESEARCH_HINTS = ("search", "latest", "news", "look up", "research", "find online",
                   "who is", "current", "browse")
_WRITING_HINTS = ("write a", "draft", "essay", "blog", "email", "letter", "summary of",
                  "report on", "article")


def _heuristic_route(task: str, last_err: Exception) -> dict:
    t = (task or "").lower()
    raw = _cache_key(task)            # the user's request, minus any context preamble
    if len(raw.strip()) <= 12:        # trivial / empty -> stay at tier 1 (don't escalate)
        tier, tt = 1, "chat"
    elif any(h in t for h in _CODING_HINTS):
        tier, tt = 2, "coding"
    elif any(h in t for h in _RESEARCH_HINTS):
        tier, tt = 2, "research"
    elif any(h in t for h in _WRITING_HINTS):
        tier, tt = 2, "writing"
    else:
        tier, tt = 2, "general"
    return {"tier": tier, "task_type": tt,
            "requires_web": tt == "research",
            "reason": f"heuristic fallback ({type(last_err).__name__})",
            "routed_model": registry.model_for_tier(f"tier{tier}", task_type=tt)}


def classify(task: str, budget: Budget = None) -> dict:
    key = _cache_key(task)
    if key and key in _CACHE:
        cached = dict(_CACHE[key])
        cached["routed_model"] = registry.model_for_tier(
            f"tier{cached['tier']}", task_type=cached.get("task_type"))
        return cached
    tier_name = registry.classifier_tier()
    # Route through the classify fallback CHAIN (NVIDIA-first), so a down/rate-limited
    # primary switches model instead of failing the route. complete_chain already rotates
    # keys within each model; the outer retry below covers a transient that exhausts it.
    chain = registry.model_chain(tier_name, task_type="classify")
    last_err = None
    # Try each model in the classify chain until one returns PARSEABLE routing JSON. A model
    # that errors OR returns non-JSON / empty content is skipped for the next — so one flaky
    # classifier reply no longer sinks the whole route to the heuristic (observed: a healthy
    # model returning junk/empty output dropped straight to the keyword fallback).
    # complete_chain([model]) keeps per-model key rotation; only if EVERY model fails do we
    # fall to the heuristic below.
    for model in chain:
        try:
            resp, _ = complete_chain(
                [model],
                [{"role": "system", "content": CLASSIFIER_SYS},
                 {"role": "user", "content": task}],
                max_tokens=200, budget=budget, temperature=0,
            )
            if not getattr(resp, "choices", None):
                raise ValueError("empty response (no choices)")
            msg = resp.choices[0].message
            # Some reasoning models leave `content` empty and put everything (incl. the JSON)
            # in `reasoning_content` — fall back to it so we don't drop to the heuristic when
            # the model actually answered.
            txt = (getattr(msg, "content", None)
                   or getattr(msg, "reasoning_content", None) or "").strip()
            data = _extract_route_json(txt)   # robust: strips reasoning/fences, balanced-brace parse
            assert data["tier"] in (1, 2, 3)
            # Category is exposed as "task_type" so it never collides with the event-level
            # "type" key the orchestrator adds. Tolerate an older model still emitting "type".
            data["task_type"] = data.pop("type", data.get("task_type", "unknown"))
            data.setdefault("requires_web", False)
            data.setdefault("reason", "")
            # Show the model the AGENT will actually use (task-aware chain primary), not the
            # tier-cheapest — otherwise the UI shows a free NIM model while a coding task runs
            # on the paid DeepSeek chain.
            data["routed_model"] = registry.model_for_tier(
                f"tier{data['tier']}", task_type=data.get("task_type"))
            if key:                                  # cache only successful classifications
                if len(_CACHE) >= _CACHE_MAX:
                    _CACHE.pop(next(iter(_CACHE)))   # FIFO eviction
                _CACHE[key] = dict(data)
            return data
        except BudgetExceeded:
            raise   # a real budget stop must propagate, never be masked as a fallback
        except Exception as e:
            last_err = e
            if _is_transient(e):
                time.sleep(_BACKOFF_SECONDS)   # brief backoff before the next model
            continue

    # Safe fallback: a keyword heuristic picks tier+type (capped at tier 2 — a single
    # specialist, never the tool-heavy planner) instead of dumping everything to
    # tier-1/"unknown". The agent loop's own MAX_TOOL_ROUNDS still guards any tool use.
    return _heuristic_route(task, last_err)
