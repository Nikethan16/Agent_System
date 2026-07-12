"""
agents.py — the AGENT REGISTRY (loads config/agents.yaml) + the dispatcher.

Mirrors the model registry's philosophy: agents are data. Adding an agent is a YAML
entry, and because the dispatcher builds its menu from this registry at call time, a
new agent is immediately selectable with zero code changes.
"""
import os
import re
import json
import threading

import yaml

from .registry import registry as model_registry
from .agent import run_agent
from .llm import complete_chain, Budget
from .tools import project_notes_block
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


# ---- tier helpers (orchestration issue #4) ---------------------------------
def _tier_num(t) -> int:
    try:
        return int(str(t).lower().replace("tier", "").strip())
    except (TypeError, ValueError):
        return 2


def _effective_tier(agent_tier, routed_tier) -> str:
    """The tier to actually run at. A trivial (tier-1) task routed to a tier-2
    specialist (general/research) should NOT pay a tier-2 model — use the CHEAPER
    of the two so the cost-tier separation holds (orchestration issue #4)."""
    if routed_tier is None:
        return agent_tier
    return f"tier{min(_tier_num(agent_tier), _tier_num(routed_tier))}"


# ---- running an agent -------------------------------------------------------
# Behavior overlays (patterns ported from OpenCode's MIT-licensed prompts — adapted
# wording, tuned for open models; attribution in THIRD_PARTY.md). Composed onto an
# agent's YAML prompt by capability, so the role prompt stays declarative and the
# hard-won behavioral rules live in ONE place:
#   _EDIT_OVERLAY  -> any agent that can write/edit files
#   _EXEC_OVERLAY  -> any agent that can execute (run_bash)
# Each rule targets a NAMED open-model failure mode (the OpenCode research, 2026-07):
# answering with code blocks instead of tool calls, phantom imports, drive-by
# rewrites, ending the turn on an announcement, and claiming success untested.
_EDIT_OVERLAY = (
    "\n\nFILE RULES: Code that only appears in your reply is NOT saved and has no "
    "effect — every file change must go through write_file/edit_file. If a request "
    "could be read as either a question or a job to do, treat it as a job and use "
    "your tools. Make the smallest correct change that achieves the goal — no "
    "drive-by refactors or unrequested rewrites. Never assume a library is "
    "available, even a famous one: before importing it, confirm the project already "
    "uses it (dependency file or neighboring imports). Read a file before you edit "
    "it. Debug to the root cause, not the symptom — never patch around an error you "
    "don't understand; if a result surprises you, revise your assumptions before "
    "editing more code."
)
_EXEC_OVERLAY = (
    "\n\nPERSISTENCE: Keep working until the task is genuinely DONE and VERIFIED — do not stop "
    "early or hand back partial work. If you wrote or changed code you MUST run it (run_bash) "
    "and confirm it works; when a command or test fails, read the error, fix it, and re-run "
    "until it passes. Never say something works without having actually executed it. Prefer "
    "making one concrete edit and running it over describing what you would do. "
    "The single most common failure on tasks like yours is declaring done without rigorous "
    "testing — assume your first version has a bug until a real run proves otherwise. If you "
    "say you are about to run a command or take a step, actually do it in this same turn; "
    "never end your turn on an announcement."
)


def _overlays_for(a) -> str:
    tools = set(a.tools or [])
    out = ""
    if tools & {"write_file", "edit_file"}:
        out += _EDIT_OVERLAY
    if "run_bash" in tools:
        out += _EXEC_OVERLAY
    return out


def run(agent_id, task, budget=None, emit=None, approve=None, context="",
        max_tokens=None, stream=False, task_type=None, skills=None, tier=None,
        use_skills=True, verify_run=False, max_rounds=None):
    a = agents.get(agent_id) or agents.get(agents.fallback_id())
    # Cost-first selection prefers a cheap model good at this task / the agent's specialty.
    tt = task_type or (a.capabilities[0] if a.capabilities else None)
    eff_tier = _effective_tier(a.tier, tier)
    # The fallback CHAIN for this agent (primary first); run_agent falls back down it
    # if a model is rate-limited/down. model_chain[0] is the same primary as before.
    models = model_registry.model_chain(eff_tier, task_type=tt)
    mt = max_tokens or model_registry.max_tokens_for_tier(eff_tier)

    # SKILLS (Claude-style): pick relevant skills for this task, stage their bundled
    # scripts into the workspace, and inject their guidance — this lifts output quality.
    # `skills` lets the lead agent EXPLICITLY pull a skill it judged relevant; the rest
    # are auto-matched. (Progressive disclosure: only selected skills' bodies load.)
    chosen = skill_lib.select(task, agent=a, names=skills, auto=use_skills)
    skctx = ""
    if chosen:
        skill_lib.stage(chosen)
        skctx = skill_lib.context(chosen)
        if emit:
            emit({"type": "skill", "agent": a.id, "skills": [s.name for s in chosen]})

    extra = []
    # Project rules (AGENTS.md / CLAUDE.md in the workspace, OpenCode-style): agents
    # follow the project's own build/test commands and conventions instead of
    # rediscovering them each run. Tool-less chat agents skip it (no files to obey);
    # empty workspace = empty string = zero cost.
    if a.tools:
        notes = project_notes_block()
        if notes:
            extra.append(notes)
    if skctx:
        extra.append(skctx)
    if context:
        extra.append("--- shared context from other agents (read-only) ---\n" + context)
    full = task if not extra else task + "\n\n" + "\n\n".join(extra)
    # Each agent runs under its OWN sub-budget (caps it locally; still counts
    # against the shared run budget so the global cap can't be bypassed).
    b = budget.child(max_usd=a.max_usd, max_iterations=a.max_iterations) if budget is not None else None
    system = a.prompt + _overlays_for(a)
    return run_agent(
        full, system, models[0], max_tokens=mt, budget=b, models=models,
        label=a.id, emit=emit, allowed_tools=a.tools, approve=approve, stream=stream,
        verify_run=verify_run, max_rounds=max_rounds,
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
    # Dispatch through the classify fallback chain too, so a down primary switches model
    # rather than dropping straight to the keyword fallback.
    chain = model_registry.model_chain(agents.dispatcher_tier(), task_type="classify")
    # NOTE: _DISPATCH_SYS contains a literal JSON example with braces, so we must NOT
    # use str.format() (it would treat {"agent"} as a field). Use replace().
    system = _DISPATCH_SYS.replace("{menu}", menu)
    txt = ""
    try:
        resp, _ = complete_chain(
            chain,
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
    # Tolerate a model that replied with the bare id (or wrapped it in prose) but
    # not clean JSON, before dropping to keyword matching — this is what made the
    # dispatcher silently fall back in live traces (orchestration issue #4).
    low = txt.lower()
    for a in cat:
        if re.search(rf"\b{re.escape(a.id)}\b", low):
            return a.id, "matched agent id in response"
    return _fallback_select(task), "fallback (keyword match)"
