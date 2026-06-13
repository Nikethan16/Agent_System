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
import time

from .llm import complete_chain, Budget, BudgetExceeded
from .registry import registry

CLASSIFIER_SYS = (
    "You are a task router. Output ONLY valid JSON, no prose, no code fences:\n"
    '{"tier": 1|2|3, "task_type": "coding"|"writing"|"research"|"math"|"data", '
    '"requires_web": true|false, "reason": "<=8 words"}\n'
    "Tier 1 = trivial (summarize, classify, format, short answer).\n"
    "Tier 2 = moderate (write code, draft a report, analyze).\n"
    "Tier 3 = hard (multi-file code, deep reasoning, architecture, long research)."
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


def classify(task: str, budget: Budget = None) -> dict:
    key = _cache_key(task)
    if key and key in _CACHE:
        cached = dict(_CACHE[key])
        cached["routed_model"] = registry.model_for_tier(f"tier{cached['tier']}")
        return cached
    tier_name = registry.classifier_tier()
    # Route through the classify fallback CHAIN (NVIDIA-first), so a down/rate-limited
    # primary switches model instead of failing the route. complete_chain already rotates
    # keys within each model; the outer retry below covers a transient that exhausts it.
    chain = registry.model_chain(tier_name, task_type="classify")
    last_err = None
    for attempt in range(_RETRIES + 1):
        try:
            resp, _ = complete_chain(
                chain,
                [{"role": "system", "content": CLASSIFIER_SYS},
                 {"role": "user", "content": task}],
                max_tokens=200, budget=budget, temperature=0,
            )
            if not getattr(resp, "choices", None):
                raise ValueError("empty response (no choices)")
            txt = resp.choices[0].message.content.strip()
            txt = txt[txt.find("{"): txt.rfind("}") + 1]   # tolerate stray text
            data = json.loads(txt)
            assert data["tier"] in (1, 2, 3)
            # Category is exposed as "task_type" so it never collides with the
            # event-level "type" key the orchestrator adds (e.g. "route"). Tolerate
            # an older model still emitting "type".
            data["task_type"] = data.pop("type", data.get("task_type", "unknown"))
            data.setdefault("requires_web", False)
            data.setdefault("reason", "")
            data["routed_model"] = registry.model_for_tier(f"tier{data['tier']}")
            if key:                                  # cache only successful classifications
                if len(_CACHE) >= _CACHE_MAX:
                    _CACHE.pop(next(iter(_CACHE)))   # FIFO eviction
                _CACHE[key] = dict(data)
            return data
        except BudgetExceeded:
            raise   # a real budget stop must propagate, never be masked as a fallback
        except Exception as e:
            last_err = e
            if attempt < _RETRIES and _is_transient(e):
                time.sleep(_BACKOFF_SECONDS)   # brief backoff, then retry once
                continue
            break

    # Safe fallback: route DOWN to tier 1 (cheap, single specialist) rather than
    # escalating. The agent loop's own MAX_TOOL_ROUNDS still guards any tool use.
    return {
        "tier": 1,
        "task_type": "unknown",
        "requires_web": False,
        "reason": f"fallback ({type(last_err).__name__})",
        "routed_model": registry.model_for_tier("tier1"),
    }
