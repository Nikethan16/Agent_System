"""
agents.py — the AGENT REGISTRY (loads config/agents.yaml) + the dispatcher.

Mirrors the model registry's philosophy: agents are data. Adding an agent is a YAML
entry, and because the dispatcher builds its menu from this registry at call time, a
new agent is immediately selectable with zero code changes.
"""
import os
import json
import threading

import yaml

from .registry import registry as model_registry
from .agent import run_agent
from .llm import complete, Budget
from . import skills as skill_lib

_PATH = os.environ.get(
    "AGENTS_CONFIG",
    os.path.join(os.path.dirname(__file__), "..", "config", "agents.yaml"),
)


class Agent:
    def __init__(self, d: dict):
        self.id = d["id"]
        self.label = d.get("label", d["id"])
        self.tier = d.get("tier", "tier2")
        self.tools = d.get("tools", [])
        self.capabilities = d.get("capabilities", [])
        self.when_to_use = d.get("when_to_use", "")
        self.prompt = d.get("prompt", "You are a helpful agent.")
        # Optional per-agent budget caps (least-spend); default = the run budget.
        self.max_usd = d.get("max_usd")
        self.max_iterations = d.get("max_iterations")


class AgentRegistry:
    def __init__(self, path: str = _PATH):
        self.path = path
        self._lock = threading.Lock()
        self.reload()

    def reload(self):
        with open(self.path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        self.defaults = cfg.get("defaults", {})
        self.agents = {a["id"]: Agent(a) for a in cfg.get("agents", [])}

    def get(self, agent_id: str):
        return self.agents.get(agent_id)

    def fallback_id(self) -> str:
        return self.defaults.get("fallback_agent", "general")

    def dispatcher_tier(self) -> str:
        return self.defaults.get("dispatcher_tier", "tier1")

    def catalog(self, exclude=("supervisor", "security-manager", "model-scout")) -> list:
        """The agents the dispatcher may choose from (hides internal-only ones)."""
        return [a for a in self.agents.values() if a.id not in exclude]


agents = AgentRegistry()


# ---- running an agent -------------------------------------------------------
def run(agent_id, task, budget=None, emit=None, approve=None, context="",
        max_tokens=None, stream=False, task_type=None, skills=None):
    a = agents.get(agent_id) or agents.get(agents.fallback_id())
    # Cost-first selection prefers a cheap model good at this task / the agent's specialty.
    tt = task_type or (a.capabilities[0] if a.capabilities else None)
    model = model_registry.model_for_tier(a.tier, task_type=tt)
    mt = max_tokens or model_registry.max_tokens_for_tier(a.tier)

    # SKILLS (Claude-style): pick relevant skills for this task, stage their bundled
    # scripts into the workspace, and inject their guidance — this lifts output quality.
    # `skills` lets the lead agent EXPLICITLY pull a skill it judged relevant; the rest
    # are auto-matched. (Progressive disclosure: only selected skills' bodies load.)
    chosen = skill_lib.select(task, agent=a, names=skills)
    skctx = ""
    if chosen:
        skill_lib.stage(chosen)
        skctx = skill_lib.context(chosen)
        if emit:
            emit({"type": "skill", "agent": a.id, "skills": [s.name for s in chosen]})

    extra = []
    if skctx:
        extra.append(skctx)
    if context:
        extra.append("--- shared context from other agents (read-only) ---\n" + context)
    full = task if not extra else task + "\n\n" + "\n\n".join(extra)
    # Each agent runs under its OWN sub-budget (caps it locally; still counts
    # against the shared run budget so the global cap can't be bypassed).
    b = budget.child(max_usd=a.max_usd, max_iterations=a.max_iterations) if budget is not None else None
    return run_agent(
        full, a.prompt, model, max_tokens=mt, budget=b,
        label=a.id, emit=emit, allowed_tools=a.tools, approve=approve, stream=stream,
    )


# ---- the dispatcher: pick which agent handles a task ------------------------
_DISPATCH_SYS = (
    "You are an agent dispatcher. Given a TASK and a MENU of agents, choose the ONE "
    "best-suited agent. Output ONLY JSON: {\"agent\": \"<id>\", \"reason\": \"<=8 words\"}.\n"
    "Rules: questions, explanations, follow-ups, or discussion about existing work go to "
    "'general' (it answers directly). Only pick 'coder' when NEW code must be written or "
    "run. Pick 'doc' for producing a document, 'research' for looking things up.\n"
    "MENU:\n{menu}"
)

_KEYWORDS = [
    ("research", ("research", "investigate", "find out", "look up", "what should we",
                  "compare options", "latest", "sources")),
    ("image", ("image", "picture", "logo", "graphic", "illustration", "render", "photo")),
    ("frontend", ("html", "css", "frontend", "react", "web page", "webpage", "ui ", "landing")),
    ("coder", ("code", "function", "script", "bug", "test", "python", "api ", "implement",
               "refactor", "compile", "run ")),
    ("doc", ("document", "report", "write up", "readme", "summary doc", "memo")),
]


_EXPLAIN = ("explain", "what is", "what does", "what's", "how does", "how do", "why ",
            "describe", "tell me about", "walk me through", "summarize")
_MAKE = ("write", "build", "create", "implement", "generate", "make a", "add ", "fix ",
         "refactor", "debug", "run ")


def _fallback_select(task: str) -> str:
    t = task.lower()
    # Explanation / follow-up questions go to the (tool-less) general agent, NOT the
    # coder — even when the word "code" appears (e.g. "explain this code").
    if any(k in t for k in _EXPLAIN) and not any(k in t for k in _MAKE):
        return "general"
    for agent_id, kws in _KEYWORDS:
        if agent_id in agents.agents and any(k in t for k in kws):
            return agent_id
    return agents.fallback_id()


def select_agent(task: str, budget: Budget = None):
    """Returns (agent_id, reason). LLM pick from the registry menu, with a fallback."""
    cat = agents.catalog()
    menu = "\n".join(f"- {a.id}: {a.when_to_use}" for a in cat)
    model = model_registry.model_for_tier(agents.dispatcher_tier())
    # NOTE: _DISPATCH_SYS contains a literal JSON example with braces, so we must NOT
    # use str.format() (it would treat {"agent"} as a field). Use replace().
    system = _DISPATCH_SYS.replace("{menu}", menu)
    try:
        resp, _ = complete(
            model,
            [{"role": "system", "content": system},
             {"role": "user", "content": task}],
            max_tokens=120, budget=budget, temperature=0,
        )
        txt = (resp.choices[0].message.content or "").strip()
        data = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        aid = (data.get("agent") or "").strip()
        if aid in agents.agents:
            return aid, data.get("reason", "")
    except Exception:
        pass
    return _fallback_select(task), "fallback (keyword match)"
