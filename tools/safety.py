"""
safety.py — optional content-safety screening (C5).

A `safety_check` tool (+ a screen() helper) for vetting UNTRUSTED text — e.g. a fetched
web page — for harmful content or prompt-injection before an agent acts on it. Uses a
safety model when SAFETY_MODEL is set (e.g. a NIM content-safety model via LiteLLM),
otherwise a quick heuristic. Registers into core.toolbelt on import.
"""
import os

from core import toolbelt
from core.llm import complete, Budget

# Cheap heuristic patterns (used when no SAFETY_MODEL is configured).
_HEUR = ("ignore previous instructions", "ignore all previous", "disregard your instructions",
         "reveal your system prompt", "exfiltrate", "send your api key", "leak the",
         "rm -rf /", "curl http")


def screen(text: str) -> dict:
    """Return {ok: bool, reason: str}. Model-based when SAFETY_MODEL is set, else heuristic."""
    t = (text or "")[:6000]
    model = os.environ.get("SAFETY_MODEL")
    if model:
        try:
            resp, _ = complete(
                model,
                [{"role": "system", "content": "You are a content-safety classifier. Reply ONLY "
                                                "'SAFE' or 'UNSAFE: <short reason>'."},
                 {"role": "user", "content": t}],
                max_tokens=40, budget=Budget(max_usd=0.05, max_iterations=2),
            )
            out = (resp.choices[0].message.content or "").strip()
            if out.upper().startswith("UNSAFE"):
                return {"ok": False, "reason": out[:160]}
            return {"ok": True, "reason": "model: safe"}
        except Exception:
            pass   # fall through to heuristic on any provider error
    low = t.lower()
    hit = next((h for h in _HEUR if h in low), None)
    return {"ok": hit is None, "reason": (f"flagged: {hit}" if hit else "ok")}


toolbelt.register_fn(
    "safety_check", lambda text: ("SAFE" if screen(text)["ok"] else f"UNSAFE — {screen(text)['reason']}"),
    {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    "Screen untrusted text (e.g. a fetched web page) for unsafe content / prompt-injection "
    "before acting on it. Returns SAFE, or UNSAFE with a reason.", toolbelt.RISK_SAFE,
)
