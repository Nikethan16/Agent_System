"""
orchestrator.py — the SUPERVISOR, modelled on Claude Code's single-threaded master loop.

Instead of rigidly pre-decomposing a goal into fixed subtasks, a LEAD agent runs an
iterative loop (Claude-Code style):
  * it maintains a live TODO list (write_todos) — re-injected after each step so it
    never loses track,
  * it works the steps by either using tools itself OR DELEGATING a well-scoped step
    to a specialist subagent (delegate) — each subagent has its own context and CANNOT
    delegate again (depth-limited, no runaway spawning),
  * it keeps going until the whole goal is done, then writes the final answer.

Routing by difficulty (router):
  tier 1-2  -> one focused specialist agent (its own think→act→observe loop)
  tier 3    -> the LEAD master loop (todos + delegation)

Model choice is cost-first AND task-aware (registry.model_for_tier(tier, task_type)):
the lead uses a reasoning-tier model; each agent uses the cheapest model good at its job.
"""
import os
import json
import re
from concurrent.futures import ThreadPoolExecutor

from .llm import (complete, complete_chain, stream_complete, stream_complete_chain,
                  Budget, BudgetExceeded, set_run_budget, use_budget, _span_ctx, use_span_ctx)
from .registry import registry
from .router import classify
from . import agents as team
from . import toolbelt
from . import skills as skill_lib
from . import playbooks as playbook_lib
from .agent import _run_one_tool, _looks_like_raw_toolcall, _compact_messages
from .blackboard import Blackboard
from .tools import (current_workspace, using_workspace, project_notes_block, repo_map,
                    write_file, run_bash)

MAX_MASTER_ROUNDS = 16     # hard cap on lead loop iterations
MAX_DELEGATIONS = 10       # hard cap on subagent spawns per run (depth-limited too)
MAX_PARALLEL_FANOUT = int(os.environ.get("AGENT_MAX_PARALLEL", "4"))  # concurrent subagents

# Task types that warrant an automatic QA pass when review is left on "auto":
# substantive *build/analysis* work where a concrete pass/fail check adds value.
# Trivial (tier 1) and pure look-up/chat tasks are skipped to save cost + latency.
_REVIEW_TASK_TYPES = {"coding", "writing", "data", "math"}

# Tier-3 task types a SINGLE strong agent (one tight think→act→observe loop, Claude-Code/
# OpenCode style) handles BETTER than the multi-agent lead/delegate decomposition.
# A/B-verified on the VM 2026-06-22: on a hard interpreter build, a single coding agent
# produced real, fully-tested code (43 pytest passing) in 3.2 min, while the multi-agent
# tier-3 loop produced 69-byte `# To be implemented` stubs in 14.2 min — dependent build
# steps can't be parallelized and decomposition fragments the agent's context. The
# multi-agent loop stays for genuinely-INDEPENDENT work (e.g. multi-topic research).
_TIER3_SINGLE_AGENT_TYPES = {"coding"}

# Cross-domain coordination detector. The classifier returns ONE task_type, so a task that
# genuinely spans several domains (research + build + document) collapses to a single
# specialist that can't cover all of it — e.g. a research agent asked to also build and run
# code just writes the report and silently drops the code (observed in live testing). When
# the user EXPLICITLY asks for multiple coordinated parts across domains, route to the LEAD
# master loop instead so it can delegate each part to the right specialist. Deliberately
# conservative — requires BOTH explicit coordination language AND >=2 distinct domains — so
# ordinary single-domain work ("build a calculator + tests", "write a blog post") is never
# escalated into an expensive multi-agent run.
_COORD_CUES = re.compile(
    r"\b(coordinat|delegat|orchestrat|each step|multi[-\s]?part|separate steps|"
    r"as separate|different specialists|hand[-\s]?off|multiple (parts|steps|deliverables|"
    r"specialists|components))", re.I)
_DOMAIN_PATS = {
    "build": re.compile(r"\b(build|implement|code|coding|script|app\.py|module|function|"
                        r"class\b|unit test|pytest|endpoint|cli|flask|fastapi|react|\.py\b)", re.I),
    "research": re.compile(r"\b(research|search|look up|latest|current|online|web\b|"
                           r"sources?|cite|citation)", re.I),
    "document": re.compile(r"\b(document|report|comparison|summary|essay|write[-\s]?up|"
                           r"markdown|\.md\b|readme|spreadsheet|slide|presentation)", re.I),
}


def _wants_delegation(task: str) -> bool:
    """True only when the task explicitly asks to coordinate work across >=2 domains."""
    t = task or ""
    if not _COORD_CUES.search(t):
        return False
    return sum(1 for p in _DOMAIN_PATS.values() if p.search(t)) >= 2


# Genuine EXTERNAL/online research intent. STRICTER than _DOMAIN_PATS["research"] on purpose:
# bare "current"/"web" caused false positives — e.g. "report the CURRENT environment" in a
# pure-local coding task got mis-routed into a heavy research+build pipeline. Require an
# explicit online/lookup cue.
_EXTERNAL_RESEARCH = re.compile(
    r"\b(search (?:the )?(?:web|internet|online)|on the (?:web|internet)|google it|"
    r"look (?:it |them )?up online|browse the|"
    r"latest (?:news|version|release|prices?|docs?|documentation|developments?)|"
    r"current (?:news|events|prices?|version|weather|rates?)|"
    r"recent (?:news|developments?|changes?)|find out (?:about|the latest)|https?://)", re.I)

# Explicit INDEPENDENCE cues -> the task splits into parts that don't depend on each other,
# so the LEAD can run them as parallel delegations (delegate_parallel). Conservative on
# purpose: dependent work must stay a single tight loop (dependent build steps can't be
# parallelized — you can't test code before it exists).
_PARALLEL_CUES = re.compile(
    r"\b(in parallel|concurrently|simultaneously|at the same time|independent(?:ly)?|"
    r"unrelated|separate (?:modules|files|components|tasks|scripts|utilities)|"
    r"(?:each|several|multiple|three|four|3|4) (?:independent|unrelated|separate))", re.I)


def _wants_parallel(task: str) -> bool:
    """True when the task explicitly describes independent parts that can run concurrently."""
    return bool(_PARALLEL_CUES.search(task or ""))


def _wants_pipeline(task: str) -> bool:
    """True only when the task needs GENUINE external/online research AND a build component —
    the one case no lone specialist covers (a research agent has no run_bash; a coder won't
    fetch current online info). Routed to the LEAD master loop (shared context + delegation),
    NOT a rigid re-reading relay. Pure local coding never triggers this."""
    t = task or ""
    return bool(_EXTERNAL_RESEARCH.search(t) and _DOMAIN_PATS["build"].search(t))


# File-producing / document-generation intent (pptx/docx/xlsx/pdf). These tasks must ACTUALLY
# run their generator and produce the binary file, so the verify gate is armed even when the
# classifier labels them "general"/"writing" (observed: a "make a PPT" task wrote a generator
# script but never ran it -> no artifact, because verify wasn't armed). Narrow on purpose:
# only real binary-doc formats, NOT a plain markdown report/essay (the doc agent writes those
# directly with no generator to run).
_DOCGEN_INTENT = re.compile(
    r"\b(\.pptx|\.docx|\.xlsx|\.pdf|powerpoint|power\s?point|slide\s?deck|\bdeck\b|"
    r"presentation|spreadsheet|excel|workbook|word\s+document)\b", re.I)


def _produces_file(task: str) -> bool:
    """True when the task must generate an actual document/binary file (run a generator)."""
    return bool(_DOCGEN_INTENT.search(task or ""))


# "Read & understand an EXISTING repo/URL" intent. A live failure (2026-07) saw
# "understand github.com/x/y and summarize it" get classified as a coding build, escalated to
# tier-3, and handed to coder/frontend — which never fetched the repo and HALLUCINATED a
# fictional app description. Such a task must go to a single agent that can actually FETCH the
# source (repo-engineer clones + has GitHub tools), NOT the build path.
_RU_VERB = re.compile(
    r"\b(understand|summar(?:y|ise|ize|ising|izing)|explain|describe|analy[sz]e|review|"
    r"walk me through|go through|look at|get a sense|what (?:is|does|are)|tell me about)\b", re.I)
_RU_URL = ("github.com/", "gitlab.com/", "bitbucket.org/")
# Primarily a build/modify request -> don't hijack (an understand-THEN-build task routes normally).
_RU_BUILD = re.compile(
    r"\b(build|create|implement|scaffold|develop|integrate|add (?:a |the )?(?:feature|endpoint|"
    r"page|screen)|refactor|migrate|port)\b", re.I)


def _repo_understanding_agent(task: str) -> str:
    """If the task is 'read/understand/summarize an existing repo shared by URL' (not build
    one), return the agent that should FETCH it (repo-engineer: clone + GitHub tools). Empty
    otherwise. Deterministic guard against the classifier mis-routing a READ task into a build
    that never reads the source and invents a description."""
    t = task or ""
    if not any(u in t.lower() for u in _RU_URL):
        return ""                                  # only when a real repo URL is shared
    if not _RU_VERB.search(t) or _RU_BUILD.search(t):
        return ""                                  # need an understand verb, and not a build
    return "repo-engineer" if team.agents.get("repo-engineer") else ""


# Deterministic complexity signals — a cheap, robust cross-check on the classifier's tier.
# The classifier is one fast model's snap judgment and DOES under-tier big builds (observed: a
# full 7-feature app read as tier 2 -> weak flash model -> lame MVP). These signals catch that
# for free and RAISE the tier so the strong-model floor (tier 3) kicks in. Only build scope.
_BIG_SCOPE = re.compile(
    r"\b(full|complete|entire|end[- ]?to[- ]?end|production|whole app|full app|multi[- ]?page|"
    r"from scratch|full[- ]?stack|multiple (?:screens|pages|views|modules|features|components))\b",
    re.I)
_PRODUCT_NOUN = re.compile(
    r"\b(app|application|system|platform|tracker|dashboard|website|web app)\b", re.I)
# Hard-ARCHITECTURE signals — a build that needs real backend/data/security design (the deep
# test's multi-tenant Kanban scored only 3 on the old heuristic and wrongly stayed tier-2 →
# flash, because its spec used prose + `POST /path` endpoint lines, not bullet points).
_HARD_SIGNALS = re.compile(
    r"\b(multi[- ]?tenant|rbac|role[- ]?based|access[- ]control|authentication|auth|login|"
    r"permission|isolation|database|sqlite|postgres|persist(?:ence|ed)?|migration|"
    r"\bapi\b|endpoint|backend|server[- ]?side|microservice|concurren|websocket)\b", re.I)
# REST endpoint lines like "POST /users" / "GET /boards/{id}" — a strong signal of a real API.
_ENDPOINT_LINE = re.compile(r"(?mi)^\s*(?:GET|POST|PUT|DELETE|PATCH)\s+/\S")


def _difficulty_score(task: str) -> int:
    """A 0-12 deterministic complexity estimate from the request text (no model call)."""
    t = task or ""
    score = 0
    if _BIG_SCOPE.search(t):
        score += 3
    feats = len(re.findall(r"(?m)^\s*(?:\d+[.)]|[-*])\s+\S", t))   # a numbered/bulleted feature list
    score += 3 if feats >= 3 else (1 if feats == 2 else 0)
    endpoints = len(_ENDPOINT_LINE.findall(t))                     # a real REST API contract
    score += 3 if endpoints >= 3 else (1 if endpoints >= 1 else 0)
    # distinct hard-architecture signals (multi-tenant / auth / db / api / backend …)
    hard = len({m.group(0).lower() for m in _HARD_SIGNALS.finditer(t)})
    score += min(hard, 3)
    if len(t) > 600:                                              # a long, detailed spec
        score += 2
    if _PRODUCT_NOUN.search(t):
        score += 1
    return score


# Which specialist actually PRODUCES the deliverable in the pipeline's implement stage.
_IMPLEMENTER = {"coding": "coder", "frontend": "frontend", "data": "data-analyst",
                "writing": "doc", "research": "coder", "general": "coder"}


def _auto_review(tier, task_type) -> bool:
    """Decide whether to run the critic when review == 'auto' (the default).

    Tier 3 always gets QA. For tier-2 substantive work we mirror Claude Code: when the
    agent can EXECUTE its work to self-verify (the run_bash sandbox is available), trust
    its in-loop verification (it's instructed to run code/tests and report how) instead
    of paying for a redundant full critic pass. When execution ISN'T available, the
    critic earns its cost by inspecting what couldn't be run. AGENT_ALWAYS_REVIEW=1
    forces QA on regardless."""
    if tier >= 3:
        return True
    if not (tier >= 2 and task_type in _REVIEW_TASK_TYPES):
        return False
    if os.environ.get("AGENT_ALWAYS_REVIEW", "").strip().lower() in ("1", "true", "yes"):
        return True
    # Sandbox available (Docker configured) -> agent self-verifies in its loop;
    # skip the redundant critic. Check the env var, not toolbelt.names() — run_bash
    # is always registered now (CRITICAL+requires_human when no Docker) so names()
    # is not a reliable proxy for "execution is actually available".
    return not bool(os.environ.get("AGENT_BASH_DOCKER_IMAGE", "").strip())


# ---- Trivial chit-chat fast-path -------------------------------------------
# A greeting like "hi" must never hit the LLM classifier: under a provider
# rate-limit the classifier throws and falls back to tier2 + task_type
# "unknown", which can route a one-word message into a tool-capable agent that
# then spins on tool calls until the iteration cap ("stopped: iteration cap
# hit"). This deterministic guard answers obvious social messages with the
# tool-less `general` agent in a single call — impossible to loop, no extra
# model calls for routing. It is intentionally conservative: the WHOLE message
# must be social, so "hi, write me a script" is NOT caught.
_CHITCHAT_WORDS = {
    "hi", "hii", "hiii", "hiiii", "hello", "helo", "hey", "heya", "hiya", "yo",
    "sup", "hola", "howdy", "gm", "gn", "ty", "thx", "thanks", "thankyou",
    "cheers", "ok", "okay", "k", "kk", "cool", "nice", "great", "awesome",
    "lol", "lmao", "haha", "hehe", "np", "bye", "goodbye", "ciao", "yes", "no",
    "yep", "nope", "sure", "there", "morning", "hii!",
}
_CHITCHAT_PHRASES = {
    "hello there", "hey there", "hi there", "good morning", "good afternoon",
    "good evening", "good night", "thank you", "thanks a lot", "thanks so much",
    "thank you so much", "no problem", "youre welcome", "you re welcome",
    "see ya", "see you", "who are you", "what are you", "what can you do",
    "how are you", "whats up", "sounds good", "good to know",
}


def _norm_chat(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def _is_trivial_chat(text: str) -> bool:
    t = _norm_chat(text)
    if not t or len(t) > 40:
        return False
    if t in _CHITCHAT_PHRASES:
        return True
    words = t.split()
    return len(words) <= 3 and all(w in _CHITCHAT_WORDS for w in words)


def _user_request(task: str) -> str:
    """The raw user message, even when chat.py prepended memory/history context
    as `...\\n\\nNEW REQUEST: <text>`. Used so triviality is judged on what the
    user actually typed, not the assembled context."""
    marker = "NEW REQUEST:"
    i = task.rfind(marker)
    return (task[i + len(marker):] if i != -1 else task).strip()


def _resolve_review(review, tier, task_type) -> bool:
    """review is tri-state: True (always), False (never), 'auto' (decide by task)."""
    if isinstance(review, bool):
        return review
    return _auto_review(tier, task_type)

MASTER_SYS = (
    "You are the LEAD engineer on a complex task. Work like Claude Code — one loop, "
    "doing the work yourself with tools, delegating only when it genuinely helps. Deliver the "
    "SIMPLEST thing that fully solves the task — match the form to what the user actually wants "
    "to use, and don't add scope, files, or infrastructure they didn't ask for:\n"
    "1) Call write_todos to lay out a short plan (3-6 concrete steps).\n"
    "2) Work the steps: DO sequential or dependent steps YOURSELF with "
    "read_file/list_files/write_file/edit_file/run_bash — think, act, observe, repeat. "
    "DELEGATE to a specialist only for work that is genuinely independent or needs deep "
    "expertise (e.g. a dedicated researcher for web-heavy work, a data analyst for complex "
    "CSV/SQL, a frontend engineer for a large UI). For steps that are INDEPENDENT of each "
    "other, use `delegate_parallel` to run them at the same time — it's much faster. "
    "Never delegate dependent steps (you can't test before code exists — do write→test in "
    "your own loop). Read a file before you edit it; use edit_file for precise changes, "
    "write_file only for new files.\n"
    "3) After each step, update the todo statuses with write_todos.\n"
    "4) When ALL steps are done, reply with a concise final answer for the user "
    "(mention any files produced) and DO NOT call any tool in that final message.\n\n"
    "Delegate by capability — design/architecture→architect, coding→coder (small quick "
    "edits→fast-coder), web research→research, data/CSV/finance→data-analyst, documents→"
    "doc, UI/HTML→frontend, code review→code-reviewer, QA→critic. "
    "Write SELF-CONTAINED delegations: a specialist sees ONLY your instruction plus shared "
    "results — never this conversation. Every instruction MUST state (a) the exact "
    "deliverable, (b) the inputs/files to use, (c) key constraints/requirements, and (d) the "
    "acceptance check. A vague one-line delegation produces vague work. Once you have "
    "delegated a step, do NOT redo that work yourself — build on the result. Keep the plan "
    "tight and finish: ending with steps still unchecked is a failure, and if you say you "
    "are about to do something, do it in this same turn rather than ending on an "
    "announcement.\n\n"
    "When a step matches a SKILL below, pass its name in delegate's `skill` field so the "
    "specialist loads that expertise (e.g. a Word doc → 'docx', a spreadsheet → 'xlsx', "
    "slides → 'pptx', a PDF → 'pdf').\n\n"
    "SPECIALISTS:\n{menu}\n\nSKILLS:\n{skills}"
)

PLANNER_SYS = (
    "You are the lead engineer. Break the goal into 1-5 self-contained steps, ordered so "
    'prerequisites come first. Output ONLY JSON: {"subtasks": ["...", "..."]}'
)


# ---- planning (used by plan-first preview) ---------------------------------
def _make_plan(task, budget):
    chain = registry.model_chain("tier3", task_type="reasoning")
    resp, _ = complete_chain(chain, [{"role": "system", "content": PLANNER_SYS},
                                     {"role": "user", "content": task}],
                             max_tokens=600, budget=budget, temperature=0.2)
    try:
        txt = resp.choices[0].message.content
        subs = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])["subtasks"]
        assert isinstance(subs, list) and subs
        return subs
    except Exception:
        return [task]


# ---- phased build: STRONG plans -> cheap flash implements -> STRONG reviews ----------------
# Cost-effective quality for COMPLEX (tier-3) builds. The insight: an LLM is stateless, so the
# ONLY thing carried between phases is what we pass. We pass the compact PLAN artifact (not the
# planner's raw context), so the strong-model calls stay small + cheap and the bulk runs on
# flash. A stuck flash implement escalates ONCE to the strong model (quality never collapses).
_BUILD_PLANNER_SYS = (
    "You are a senior software architect. Produce a CONCRETE, step-by-step IMPLEMENTATION PLAN "
    "that a single engineer will follow to build the task below. Decide and state: the files to "
    "create/change, the data model / state shape, the key functions or components, and an ORDERED "
    "list of small, independently-checkable build steps. Be specific and buildable. Do NOT write "
    "the application code — only the plan. Honor any theme/design/constraints in the task. Keep it "
    "tight — no preamble, no filler.")


def _build_plan(task, budget, emit=None) -> str:
    """PLAN phase: a STRONG model turns the task (+ a COMPACT repo map) into a concrete plan.
    Compact in, compact out — so the frontier model costs little. This plan is the ONLY thing
    handed to the (cheap) implementer — never the planner's raw conversation."""
    rmap = ""
    try:
        rmap = repo_map(".") or ""
    except Exception:
        rmap = ""
    user = task if not rmap.strip() else f"{task}\n\nREPO MAP (context):\n{rmap[:4000]}"
    chain = registry.model_chain("tier3", task_type="planning")   # strong model chain
    try:
        resp, _ = complete_chain(chain, [{"role": "system", "content": _BUILD_PLANNER_SYS},
                                         {"role": "user", "content": user}],
                                 max_tokens=1200, budget=budget, temperature=0.2)
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""


def _phased_build(task, budget, emit, approve, review, task_type, acceptance="", stream=True):
    """STRONG plans -> cheap flash implements the plan -> STRONG reviews -> flash fixes.
    Escalates a stuck implement to the strong model. Only the compact plan is passed forward."""
    def _e(ev):
        if emit:
            emit(ev)
    # 1. PLAN (strong, compact I/O)
    _e({"type": "assign", "agent": "architect", "label": "Planner",
        "model": registry.model_for_tier("tier3", task_type="planning"),
        "reason": "phased build: plan on the strong model"})
    plan = _build_plan(task, budget, emit)
    if plan:
        try:
            write_file("plan.md", plan)
        except Exception:
            pass
        _subs = [ln.strip("-*# ").strip() for ln in plan.splitlines() if ln.strip()][:14]
        _e({"type": "plan",
            "subtasks": _subs,
            "todos": [{"text": s, "status": "pending"} for s in _subs],   # so the roadmap captures it
            "note": "implementation plan"})
    # 2. IMPLEMENT (cheap flash coder, given ONLY the compact plan)
    agent_id = "frontend" if task_type == "frontend" else "coder"
    _e({"type": "assign", "agent": agent_id, "label": "Implementer",
        "reason": "phased build: cheap coder implements the plan step by step"})
    impl = task + (f"\n\nFOLLOW THIS IMPLEMENTATION PLAN (already designed for you — execute it "
                   f"step by step, building incrementally):\n{plan}" if plan else "")
    if acceptance:
        impl += "\n\nACCEPTANCE CRITERIA (definition of done):\n" + acceptance
    # floor_tier="tier3": this IS the hard-build path — implement on a STRONG model, not the
    # cheap coder default. Fixes the deep-test finding that every task (even a multi-tenant
    # build) collapsed to the flash model. The cost-first picker still chooses the cheapest
    # AVAILABLE tier_hint>=3 model, so free frontier models are preferred when present.
    result = _do_subtask(agent_id, impl, budget, emit, approve, "", False, stream=True,
                         task_type=task_type, use_skills=True, verify_run=True, max_rounds=28,
                         floor_tier="tier3")
    # 2b. ESCALATE: a clearly-failed / unverified implement retries ONCE on the strong model.
    if _looks_failed(result) or "UNVERIFIED" in (result or ""):
        strong = registry.model_for_tier("tier3", task_type=task_type)
        _e({"type": "fallback", "agent": agent_id, "from": "flash (implement)", "to": strong,
            "reason": "implement struggled on flash -> escalate to the strong model"})
        with registry.use_model_override(strong):
            result = _do_subtask(agent_id, impl, budget, emit, approve, "", False, stream=True,
                                 task_type=task_type, use_skills=True, verify_run=True, max_rounds=28)
    # 2c. DETERMINISTIC DONE-GATE (model-free, always runs): if the build has a test
    # suite it must actually be GREEN before we finish. This overrides any self-claim of
    # success and runs even when the LLM critic is skipped — it's what stops the agent
    # declaring "all tests pass" while a test is red. Bounded fix attempts so it can't loop.
    for _attempt in range(2):
        ran, green, tail = _verify_tests(emit)
        if not ran or green:
            break
        _e({"type": "critic", "passed": False, "issues": [tail],
            "summary": f"Automated gate: tests are RED ({tail}) — fixing before finishing."})
        gate_fix = (f"The test suite is NOT passing:\n{tail}\n\nRun `python -m pytest -q`, find "
                    f"the real cause, fix the CODE (never weaken or delete the tests), and make "
                    f"ALL tests pass.")
        result = _do_subtask(agent_id, gate_fix, budget, emit, approve, "", False, stream=True,
                             task_type=task_type, use_skills=True, verify_run=True, max_rounds=20)
    # 3. REVIEW (strong critic) + 4. FIX (flash). _review returns (passed, feedback_string).
    if review:
        passed, feedback = _review(task, result, budget, emit, approve, acceptance)
        if not passed and feedback:
            fix = ("A reviewer flagged issues — fix ALL of them and re-verify:\n" + feedback
                   + (f"\n\nORIGINAL PLAN:\n{plan}" if plan else ""))
            result = _do_subtask(agent_id, fix, budget, emit, approve, "", False, stream=True,
                                 task_type=task_type, use_skills=True, verify_run=True, max_rounds=20)
    return result


# ---- deterministic done-gate (model-free) ----------------------------------
def _verify_tests(emit=None):
    """Run the workspace's test suite in the sandbox and report the REAL result — never
    the model's claim. Returns (ran, passed, tail).

    ran=False (so callers don't block) when there is no suite (pytest exit 5) or execution
    isn't available (no Docker sandbox). This is model-free (no budget cost) and is what
    kills the 'critic said all-green while a test was red' failure mode."""
    out = run_bash("python -m pytest -q")
    if not out.startswith("exit="):
        return (False, True, "")            # no sandbox / blocked -> can't gate here
    first, _, body = out.partition("\n")
    try:
        code = int(first.split("=", 1)[1].strip())
    except (ValueError, IndexError):
        return (False, True, "")
    if code == 5:                            # pytest: no tests collected -> nothing to gate
        return (False, True, "")
    tail = ""
    for line in reversed([ln for ln in body.splitlines() if ln.strip()]):
        low = line.lower()
        if "passed" in low or "failed" in low or "error" in low:
            tail = line.strip()[:200]
            break
    passed = (code == 0)
    if emit:
        emit({"type": "tool", "name": "verify_tests", "result": f"exit={code} {tail}"[:200]})
    return (True, passed, tail or f"pytest exit={code}")


# ---- a single specialist step (with optional QA retry) ---------------------
def _review(task, result, budget, emit, approve, acceptance=""):
    def _emit(ev):
        if emit:
            emit(ev)
    rubric = (f"\n\nACCEPTANCE CRITERIA (the user's definition of done — judge PASS/FAIL "
              f"against THESE specifically):\n{acceptance}") if acceptance else ""
    prompt = (f"TASK:\n{task}\n\nPRODUCED RESULT:\n{result}{rubric}\n\n"
              "Inspect the workspace files and run tests if useful, then judge it.")
    raw = team.run("critic", prompt, budget=budget, emit=emit, approve=approve)
    try:
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        passed, issues, summary = bool(data.get("pass")), data.get("issues", []), data.get("summary", "")
    except Exception:
        # A verdict we can't parse is NOT a pass — defaulting to True is exactly how a
        # false-green slips through. Treat it as a failure so the fix loop engages.
        passed, issues, summary = False, ["critic verdict was unparseable"], "(unparseable verdict — treated as FAIL)"
    # DETERMINISTIC GATE: if there's a real test suite, it must actually be green. This
    # overrides a model 'pass' claim when tests are red (the false-green killer).
    ran, tests_green, tail = _verify_tests(emit)
    if ran and not tests_green:
        passed = False
        issues = list(issues) + [f"Test suite is NOT green: {tail}"]
        summary = f"Tests FAILED ({tail}). " + (summary or "")
    elif ran and tests_green:
        summary = (summary or "") + f" [verified: {tail}]"
    _emit({"type": "critic", "passed": passed, "issues": issues, "summary": summary})
    return passed, summary + ("\n- " + "\n- ".join(issues) if issues else "")


# Markers an agent emits when it FAILED rather than produced real work (from agent.py's
# graceful error/limit handling). Used to trigger an automatic retry (A2).
_FAIL_MARKERS = ("(stopped:", "(the model provider returned an error", "(provider error",
                 "(the model returned an empty")


def _looks_failed(r) -> bool:
    s = (r or "").strip().lower()
    return (not s) or s.startswith(_FAIL_MARKERS)


def _do_subtask(agent_id, task, budget, emit, approve, context, review, stream=False,
                task_type=None, acceptance="", tier=None, use_skills=True,
                verify_run=False, max_rounds=None, floor_tier=None):
    # verify_run / max_rounds are set by the caller (only the tier-3 build path turns the
    # verification gate on + raises the round cap) — a trivial snippet isn't forced to run.
    # floor_tier raises the model floor (hard builds implement on a strong model).
    r = team.run(agent_id, task, budget=budget, emit=emit, approve=approve,
                 context=context, stream=stream, task_type=task_type, tier=tier,
                 use_skills=use_skills, verify_run=verify_run, max_rounds=max_rounds,
                 floor_tier=floor_tier)
    # A2: if the agent errored / gave up / returned nothing, retry once with a nudge
    # (the model fallback chain has already handled provider-down within the run).
    if _looks_failed(r):
        if emit:
            emit({"type": "retry", "agent": agent_id, "reason": "previous attempt failed"})
        r = team.run(agent_id, task + "\n\n(Your previous attempt failed or was cut off — "
                     "try again and give a focused, complete result.)",
                     budget=budget, emit=emit, approve=approve, context=context,
                     stream=stream, task_type=task_type, tier=tier, use_skills=use_skills,
                     verify_run=verify_run, max_rounds=max_rounds, floor_tier=floor_tier)
    if review:
        passed, feedback = _review(task, r, budget, emit, approve, acceptance=acceptance)
        if not passed:
            fix = f"{task}\n\nA QA reviewer found issues — fix them:\n{feedback}"
            r = team.run(agent_id, fix, budget=budget, emit=emit, approve=approve,
                         context=context, stream=stream, task_type=task_type, tier=tier,
                         use_skills=use_skills, verify_run=verify_run, max_rounds=max_rounds,
                         floor_tier=floor_tier)
    return r


# ---- parallel agent fan-out (shared by the pipeline's research stage) --------
def _run_agents_parallel(specs, budget, emit, approve):
    """Run several GENUINELY-INDEPENDENT agent tasks CONCURRENTLY and return
    [(agent_id, result), ...] in the same order as `specs`.

    Each spec is a dict: {agent, instruction, context?, task_type?, skills?}. Worker
    threads don't inherit this thread's contextvars, so — exactly like the LEAD loop's
    delegate_parallel — we capture the run's workspace, budget, and trace span here and
    re-bind all three inside each worker (else parallel agents would use the DEFAULT
    ./workspace, escape the run budget, and lose their trace span). Per-task failures are
    isolated so one failing branch can't discard its siblings; a real BudgetExceeded still
    propagates so the global cap halts the run."""
    ws_root = current_workspace()
    span_root = _span_ctx.get()
    override = registry.get_model_override()

    def _one(spec):
        with using_workspace(ws_root), use_budget(budget), use_span_ctx(span_root), \
                registry.use_model_override(override):
            aid = (spec.get("agent") or "general").strip()
            if aid not in team.agents.agents:
                aid = team._fallback_select(spec.get("instruction", ""))
            instruction = spec.get("instruction") or ""
            ctx, tt, sk = spec.get("context", ""), spec.get("task_type"), spec.get("skills")
            try:
                r = team.run(aid, instruction, budget=budget, emit=emit, approve=approve,
                             context=ctx, task_type=tt, skills=sk)
                if _looks_failed(r):     # retry a failed branch once (mirrors _run_delegation)
                    r = team.run(aid, instruction + "\n\n(Previous attempt failed — retry carefully.)",
                                 budget=budget, emit=emit, approve=approve, context=ctx,
                                 task_type=tt, skills=sk)
            except BudgetExceeded:
                raise
            except Exception as e:
                r = f"(parallel task failed: {type(e).__name__}: {e})"
            return aid, r

    workers = max(1, min(len(specs), MAX_PARALLEL_FANOUT))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_one, specs))


_RESEARCH_SPLIT_SYS = (
    "You split a research goal into INDEPENDENT sub-questions that can be investigated in "
    "parallel (no sub-question depends on another's answer). Only split when the goal really "
    "has separable parts; a single focused topic stays ONE question. Output ONLY JSON: "
    '{"questions": ["...", "..."]}. Return exactly one question when it is not decomposable, '
    "and at most 4.")


def _split_research(task, budget, max_q=None):
    """Decompose a research goal into independent sub-questions for parallel fan-out.
    Returns [] when it can't split (caller then runs a single research pass)."""
    max_q = max_q or MAX_PARALLEL_FANOUT
    chain = registry.model_chain("tier1", task_type="classify")
    try:
        resp, _ = complete_chain(chain, [{"role": "system", "content": _RESEARCH_SPLIT_SYS},
                                         {"role": "user", "content": task}],
                                 max_tokens=300, budget=budget, temperature=0)
        txt = resp.choices[0].message.content or ""
        qs = json.loads(txt[txt.find("{"): txt.rfind("}") + 1]).get("questions", [])
        qs = [q.strip() for q in qs if isinstance(q, str) and q.strip()]
        return qs[:max_q]
    except Exception:
        return []


# ---- the LEAD master loop (Claude-Code style) ------------------------------
def _todos_text(todos):
    mark = {"done": "x", "in_progress": "~"}
    return "\n".join(f"[{mark.get(t.get('status'), ' ')}] {t.get('text', '')}" for t in todos)


def _master_tool_schemas():
    def obj(props, req):
        return {"type": "object", "properties": props, "required": req}
    meta = [
        {"type": "function", "function": {
            "name": "write_todos",
            "description": "Create or update the plan: the full ordered todo list.",
            "parameters": obj({"todos": {"type": "array", "items": {"type": "object", "properties": {
                "text": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "in_progress", "done"]}}}}}, ["todos"])}},
        {"type": "function", "function": {
            "name": "delegate",
            "description": "Hand a well-scoped step to a specialist agent; it returns the result. "
                           "The specialist sees ONLY your instruction + shared results, not this chat.",
            "parameters": obj({"agent": {"type": "string"},
                               "instruction": {"type": "string",
                                               "description": "A COMPLETE, self-contained task: the exact "
                                                              "deliverable, the inputs/files to use, key "
                                                              "constraints, and the acceptance check."},
                               "skill": {"type": "string",
                                         "description": "Optional skill name to load for this step "
                                                        "(e.g. docx, xlsx, pptx, pdf)."}},
                              ["agent", "instruction"])}},
        {"type": "function", "function": {
            "name": "delegate_parallel",
            "description": "Run several INDEPENDENT steps AT THE SAME TIME (e.g. research two "
                           "topics, or build two unrelated files). Use this instead of repeated "
                           "delegate calls whenever the steps don't depend on each other — it's "
                           "much faster. Do NOT use it for dependent steps (can't test before code "
                           "exists). Returns all results together.",
            "parameters": obj({"tasks": {"type": "array", "items": {"type": "object", "properties": {
                "agent": {"type": "string"},
                "instruction": {"type": "string",
                                "description": "A COMPLETE, self-contained task (deliverable, inputs, "
                                               "constraints, acceptance check)."},
                "skill": {"type": "string"}}, "required": ["agent", "instruction"]}}}, ["tasks"])}},
    ]
    return meta + toolbelt.schemas_for(["read_file", "list_files", "grep", "glob",
                                        "write_file", "edit_file", "run_bash"])


def _master_loop(task, budget, emit, approve, review, initial_todos=None, task_type=None,
                 acceptance="", stream=False):
    def _emit(ev):
        if emit:
            emit(ev)

    def _fb(frm, to, why):
        _emit({"type": "fallback", "agent": "lead", "from": frm, "to": to, "reason": why})

    # The LEAD's fallback chain (DeepSeek V4 Pro -> Nemotron Super -> ... per routing).
    chain = registry.model_chain("tier3", task_type="reasoning")
    menu = "\n".join(f"- {a.id}: {a.when_to_use}" for a in team.agents.catalog())
    skill_menu = "\n".join(f"- {s['name']}: {s['description'][:140]}" for s in skill_lib.catalog()) or "(none)"
    system = MASTER_SYS.replace("{menu}", menu).replace("{skills}", skill_menu)
    # Project rules (AGENTS.md / CLAUDE.md in the workspace): the lead follows the
    # project's own commands/conventions and passes the relevant ones into delegations.
    # Wrapped as untrusted DATA (the file is workspace-writable / may come from a cloned
    # repo) — benign conventions may be followed, but it can't override task or safety.
    _notes = project_notes_block()
    if _notes:
        system += "\n\n" + _notes
    if acceptance:
        system += ("\n\nACCEPTANCE CRITERIA (the user's definition of done — the result MUST "
                   "satisfy ALL of these; have the critic verify them):\n" + acceptance)
    if review:
        system += "\n- Before finishing, delegate a QA check to 'critic' and fix anything it flags."

    # PLAYBOOK: the proven path for this task type (default backup path if uncovered).
    # We seed the todo list from it + inject it as guidance, so the LEAD follows a
    # predictable understand->plan->build->validate->review flow with the right specialist
    # per phase. (Skipped when resuming an already-approved plan via initial_todos.)
    phases = [] if initial_todos else playbook_lib.select(task_type)
    if phases:
        system += "\n\n" + playbook_lib.guidance(phases)

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": task}]

    # Start from an explicit plan so the breakdown is grounded + visible: the playbook's
    # phases when available, else a model-invented plan (the deep fallback).
    todos = list(initial_todos or [])
    if not todos:
        todos = playbook_lib.as_todos(phases) or \
            [{"text": s, "status": "pending"} for s in _make_plan(task, budget)]

    # ONE live checklist, not a wall of repeated plans: overlay progress (first
    # `done` steps complete, the next in-progress) and emit a `plan` event ONLY when
    # the rendered checklist actually changed. This both kills the duplicate-plan
    # spam and makes the UI markers advance as work happens.
    plan_state = {"sig": None, "done": 0}

    def _emit_plan():
        items = [{"text": t.get("text", ""),
                  "status": ("done" if i < plan_state["done"]
                             else "in_progress" if i == plan_state["done"] else "pending")}
                 for i, t in enumerate(todos)]
        sig = json.dumps([(t["text"], t["status"]) for t in items])
        if sig == plan_state["sig"]:
            return
        plan_state["sig"] = sig
        _emit({"type": "plan", "subtasks": [t["text"] for t in items], "todos": items})

    _emit_plan()
    messages.append({"role": "user",
                     "content": ("Here is the plan. Work through it step by step — delegate each "
                                 "step to the right specialist (or do small steps yourself), update "
                                 "the todos as you go, then give the final answer:\n" + _todos_text(todos))})

    board = Blackboard()
    schemas = _master_tool_schemas()
    rounds, delegations = 0, 0
    raw_repaired = False        # one-shot guard: lead leaked a raw tool call (#1)
    # #3: stop the lead re-emitting the same plan forever before doing real work.
    last_todos_sig = None       # text of the last todo list written
    replan_repeats = 0          # consecutive write_todos calls with an identical plan
    plan_only_rounds = 0        # consecutive rounds whose ONLY action was (re)planning
    near_cap_nudged = False     # one-shot near-step-limit synthesis nudge (#2)

    # delegate_parallel runs each step in a ThreadPoolExecutor worker, and worker threads
    # do NOT inherit this thread's contextvars. Capture the run's workspace, span context,
    # and budget here so each parallel delegation re-binds all three — otherwise parallel
    # agents would silently use the DEFAULT ./workspace and lose the trace span.
    ws_root = current_workspace()
    span_root = _span_ctx.get()
    override = registry.get_model_override()

    def _run_delegation(item, step):
        """Run ONE delegated step (used by both delegate and delegate_parallel).
        Returns (agent_id, result). Safe to call from worker threads — Budget and the
        Blackboard are thread-safe, team.run gives each agent its own sub-budget, and the
        workspace, run budget, span context, and model pin are re-bound here so worker
        threads land in the right sandbox, charge the right budget, attribute costs to the
        right trace, and honor the same pinned model as the lead."""
        with using_workspace(ws_root), use_budget(budget), use_span_ctx(span_root), \
                registry.use_model_override(override):
            agent_id = (item.get("agent") or "general").strip()
            if agent_id not in team.agents.agents:
                agent_id = team._fallback_select(item.get("instruction", ""))
            agent = team.agents.get(agent_id)
            instruction = item.get("instruction") or item.get("task") or ""
            skill_arg = item.get("skill")
            skills = [skill_arg] if isinstance(skill_arg, str) and skill_arg.strip() else None
            _emit({"type": "assign", "agent": agent_id, "label": getattr(agent, "label", agent_id),
                   "model": registry.model_for_tier(getattr(agent, "tier", "tier2")),
                   "subtask": instruction, "reason": "delegated by lead", "step": step,
                   "skill": skill_arg or None})
            r = team.run(agent_id, instruction, budget=budget, emit=emit,
                         approve=approve, context=board.digest(), skills=skills)
            if _looks_failed(r):     # A2: retry a failed delegated step once
                _emit({"type": "retry", "agent": agent_id, "reason": "delegated step failed"})
                r = team.run(agent_id, instruction + "\n\n(Previous attempt failed — retry carefully.)",
                             budget=budget, emit=emit, approve=approve, context=board.digest(), skills=skills)
            board.post(agent_id, f"step-{step}", f"{instruction}\n{r}")
            return agent_id, r

    while True:
        # Mid-run steering: absorb any instructions the user injected WHILE we were working
        # (via the WS "steer" message) — fold them in as new user turns so the lead adjusts
        # its plan on the next round instead of the user having to stop + restart.
        for _inj in budget.drain_injections():
            messages.append({"role": "user",
                             "content": "(New instruction from the user, sent mid-run — fold "
                                        "this into your plan and address it): " + _inj})
            _emit({"type": "steered", "agent": "lead", "text": _inj[:200], "applied": True})
        force_final = rounds >= MAX_MASTER_ROUNDS
        active_tools = None if force_final else schemas
        # Compact older turns when the lead's history grows large (root fix for #2).
        messages = _compact_messages(messages, budget=budget, emit=emit, label="lead")
        max_tok = registry.max_tokens_for_tier("tier3")
        try:
            if stream:
                # Stream the lead's tokens so the UI shows a live rolling answer.
                # on_token fires for content pieces; tool-call deltas are assembled silently.
                msg_dict, _ = stream_complete_chain(
                    chain, messages, tools=active_tools, max_tokens=max_tok,
                    budget=budget, on_fallback=_fb,
                    on_token=lambda t: _emit({"type": "agent_token", "agent": "lead", "text": t}),
                    on_reasoning=lambda t: _emit({"type": "thinking", "agent": "lead", "text": t}))
                msg_content = msg_dict.get("content") or ""
                msg_tool_calls = msg_dict.get("tool_calls") or []
                messages.append(msg_dict)
            else:
                resp, _ = complete_chain(chain, messages, tools=active_tools, max_tokens=max_tok,
                                         budget=budget, on_fallback=_fb)
                if not getattr(resp, "choices", None):
                    # Provider returned NO choices (free-tier rate-limit / safety filter).
                    _emit({"type": "error", "agent": "lead",
                           "text": "empty response from model (often a free-tier rate limit)"})
                    return (_finalize_from_board(board, task, budget, emit, stream) or
                            "(The model returned an empty response — often a free-tier rate "
                            "limit. Wait a moment and try again.)")
                msg = resp.choices[0].message
                msg_content = msg.content or ""
                msg_tool_calls = getattr(msg, "tool_calls", None) or []
                messages.append(msg.model_dump() if hasattr(msg, "model_dump") else dict(msg))
        except BudgetExceeded as e:
            _emit({"type": "limit", "agent": "lead", "text": str(e)})
            return _finalize_from_board(board, task, budget, emit, stream) or f"(stopped: {e})"
        except Exception as e:
            _emit({"type": "error", "agent": "lead", "text": f"{type(e).__name__}: {e}"})
            return _finalize_from_board(board, task, budget, emit, stream) or f"(provider error: {type(e).__name__})"

        # In non-stream mode, emit the lead's reasoning as a "thought" bubble when tool
        # calls follow. In stream mode the tokens already fired via agent_token; emit
        # "done" to close that live segment before delegation starts so the bubbles don't mix.
        if msg_content and msg_tool_calls:
            if stream:
                _emit({"type": "done", "agent": "lead"})
            else:
                _emit({"type": "thought", "agent": "lead", "text": msg_content})

        if not msg_tool_calls:
            # #1: never surface raw tool-call markup as the final answer. Re-prompt
            # once for a clean answer; if it persists, synthesize from the blackboard.
            if _looks_like_raw_toolcall(msg_content) and not force_final:
                _emit({"type": "retry", "agent": "lead",
                       "reason": "lead emitted a raw tool call as text"})
                if not raw_repaired:
                    raw_repaired = True
                    messages.append({"role": "user", "content":
                        "Your last message contained raw tool-call markup, not a real tool "
                        "call or a clean answer. Issue a proper tool call, or give the final "
                        "answer with NO tool-call syntax."})
                    rounds += 1
                    continue
                return _finalize_from_board(board, task, budget, emit, stream) or (
                    "(The model emitted malformed tool-call output; please retry.)")
            # #2: at the hard cap, don't return raw/failed text — synthesize a real
            # answer from the blackboard (mitigation; root fix = compaction, phase 2).
            if force_final and (_looks_like_raw_toolcall(msg_content) or _looks_failed(msg_content)):
                return (_finalize_from_board(board, task, budget, emit, stream)
                        or msg_content
                        or "(Stopped at the step limit without a clean answer — please retry.)")
            # The lead finished — mark every step complete so the checklist shows done.
            if todos:
                plan_state["done"] = len(todos)
                _emit_plan()
            return msg_content or _finalize_from_board(board, task, budget, emit, stream)

        did_work = False          # any real action this round (delegate / file tool)?
        called_writetodos = False
        for tc in msg_tool_calls:
            # Tool calls come as objects (non-stream) or dicts (stream path) — normalize.
            if isinstance(tc, dict):
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments")
                tc_id = tc.get("id")
            else:
                name = tc.function.name
                raw_args = tc.function.arguments
                tc_id = tc.id
            try:
                args = json.loads(raw_args or "{}")
            except json.JSONDecodeError:
                args = {}

            if name == "write_todos":
                called_writetodos = True
                new_todos = args.get("todos") or todos
                sig = _todos_text(new_todos).strip()
                if sig and sig == last_todos_sig:
                    replan_repeats += 1
                else:
                    replan_repeats = 0
                    last_todos_sig = sig
                    todos = new_todos      # only ADOPT a genuinely new plan
                # #3: after the FIRST identical re-plan, REFUSE further re-planning — don't
                # adopt or re-emit it; force the lead to start executing. (Prevents the
                # "re-emit the same 7-step plan for 5 minutes before acting" loop.)
                if replan_repeats == 0:
                    _emit_plan()
                    result = "todos updated."
                else:
                    result = ("Plan is ALREADY set and unchanged — do NOT call write_todos "
                              "again. Execute step 1 now: delegate it or use a tool.")
            elif name == "delegate":
                if delegations >= MAX_DELEGATIONS:
                    result = "Delegation limit reached — do the remaining steps yourself or finish."
                else:
                    delegations += 1
                    did_work = True
                    _aid, result = _run_delegation(args, delegations)
            elif name == "delegate_parallel":
                items = [it for it in (args.get("tasks") or []) if isinstance(it, dict)]
                remaining = MAX_DELEGATIONS - delegations
                if remaining <= 0:
                    result = "Delegation limit reached — do the remaining steps yourself or finish."
                elif not items:
                    result = "delegate_parallel needs a non-empty 'tasks' list."
                else:
                    requested = len(items)
                    items = items[:min(remaining, MAX_PARALLEL_FANOUT)]
                    base = delegations
                    delegations += len(items)
                    did_work = True

                    # Isolate each worker: one failing parallel step must NOT discard the
                    # siblings' results (ex.map re-raises the first exception). A real
                    # BudgetExceeded still propagates so the global cap halts the run.
                    def _safe_delegation(iv):
                        try:
                            return _run_delegation(iv[1], base + 1 + iv[0])
                        except BudgetExceeded:
                            raise
                        except Exception as e:
                            aid = (iv[1].get("agent") or "general")
                            return aid, f"(parallel step failed: {type(e).__name__}: {e})"

                    # Run the independent steps CONCURRENTLY (the key pool spreads them
                    # across keys so this is genuinely faster, not just interleaved).
                    with ThreadPoolExecutor(max_workers=len(items)) as ex:
                        pairs = list(ex.map(_safe_delegation, list(enumerate(items))))
                    result = "\n\n".join(f"[{aid}] {r}" for aid, r in pairs)
                    if requested > len(items):
                        result += (f"\n\n(Note: {requested - len(items)} requested step(s) exceeded "
                                   "the parallel limit and were NOT run — issue them next.)")
            else:
                did_work = True
                result = _run_one_tool(name, args, "lead", approve, emit)

            messages.append({"role": "tool", "tool_call_id": tc_id, "content": str(result)})

        rounds += 1

        # Advance the live checklist when real work happened this round, so the UI
        # markers actually move (✓) instead of the model having to update statuses.
        if did_work and todos:
            plan_state["done"] = min(plan_state["done"] + 1, len(todos))
            _emit_plan()

        # #3: count rounds that only (re)planned without doing work; after a couple,
        # or after an identical re-plan, force the lead to start executing.
        if called_writetodos and not did_work:
            plan_only_rounds += 1
        else:
            plan_only_rounds = 0
        # #2: the near-cap synthesis nudge is evaluated FIRST and independently — a lead
        # that's stuck re-planning near the cap is exactly when this matters most, so it
        # must not be starved by the plan-repeat branch below (mitigation; the root fix is
        # within-run compaction, now shipped — see HANDOFF/BACKLOG).
        if not near_cap_nudged and rounds >= max(1, MAX_MASTER_ROUNDS - 2):
            near_cap_nudged = True
            messages.append({"role": "user", "content":
                "You are near the step limit. Stop delegating/planning and WRITE THE FINAL "
                "synthesized answer now (no tool calls), drawing on the work done so far."})
        elif todos and (replan_repeats >= 1 or plan_only_rounds >= 2):
            messages.append({"role": "user", "content":
                "The plan is set. Do NOT call write_todos again — begin executing step 1 "
                "right now (delegate it or use a tool)."})
        # Claude-style reminder injection: keep the live plan in front of the model.
        elif todos:
            messages.append({"role": "user", "content": "(reminder) current todo list:\n" + _todos_text(todos)})


def _finalize_from_board(board, task, budget, emit, stream=False):
    """If the lead ran out of budget mid-flight, synthesize what's on the blackboard."""
    digest = board.digest()
    if not digest:
        return ""
    msgs = [
        {"role": "system", "content": "Summarize the work done so far into a final answer for the user."},
        {"role": "user", "content": f"GOAL: {task}\n\nWORK DONE:\n{digest}"}
    ]
    max_tok = registry.max_tokens_for_tier("tier3")
    try:
        model = registry.model_for_tier("tier3")
        if stream and emit:
            text, _ = stream_complete(model, msgs, max_tokens=max_tok, budget=budget,
                                      on_token=lambda t: emit({"type": "agent_token",
                                                                "agent": "lead", "text": t}),
                                      on_reasoning=lambda t: emit({"type": "thinking",
                                                                   "agent": "lead", "text": t}))
            return text
        resp, _ = complete(model, msgs, max_tokens=max_tok, budget=budget)
        return resp.choices[0].message.content
    except Exception:
        return digest[:1500]


# ---- the staged pipeline: research -> plan -> implement -> review ------------
# For genuinely multi-domain work (research + build), a single specialist can't cover every
# part, and the free-tier LEAD delegates unreliably. This DETERMINISTIC manager runs each
# stage with the right specialist and passes its artifact forward via the blackboard AND the
# workspace (findings.md, design.md). Dependent stages run in sequence — you can't plan
# before the research is in, or build before the plan exists (the codebase A/B-proved that
# parallelizing a DEPENDENT build is slower + worse). The RESEARCH stage is the exception:
# it splits into independent sub-questions and investigates them CONCURRENTLY (_split_research
# + _run_agents_parallel) — genuinely independent work, the one case parallelism helps.
def _pipeline(task, budget, emit, approve, review, task_type=None, acceptance="", stream=False):
    def _emit(ev):
        if emit:
            emit(ev)

    board = Blackboard()
    # A compact map of the repo (tree + key symbols) so the architect/coder ground themselves
    # on the structure WITHOUT reading every file — the thing that lets this scale past small
    # repos. Bounded; they still read the specific files they need (or call repo_map on a subdir).
    try:
        from . import repomap
        repo_overview = repomap.build_map(current_workspace())
    except Exception:
        repo_overview = ""
    _map_ctx = (repo_overview + "\n\n") if repo_overview else ""

    need_research = bool(_DOMAIN_PATS["research"].search(task))
    impl_agent = _IMPLEMENTER.get(task_type or "", "coder")
    if team.agents.get(impl_agent) is None:
        impl_agent = "coder"
    can_run = "run_bash" in set(getattr(team.agents.get(impl_agent), "tools", None) or [])

    stage_names = ((["Research the inputs"] if need_research else [])
                   + ["Design the implementation plan", f"Implement + verify ({impl_agent})"]
                   + (["Review the change"] if (review and can_run) else []))

    def _plan(i):
        _emit({"type": "plan", "subtasks": stage_names,
               "todos": [{"text": s, "status": ("done" if j < i else "in_progress" if j == i else "pending")}
                         for j, s in enumerate(stage_names)]})

    def _assign(agent, stage, tier, tt, why):
        _emit({"type": "assign", "agent": agent, "stage": stage,
               "model": registry.model_for_tier(tier, task_type=tt), "reason": why})

    i = 0
    _plan(i)

    # STAGE 1 — RESEARCH (only when the task needs external/current info)
    if need_research:
        # Split the research goal into INDEPENDENT sub-questions and investigate them
        # CONCURRENTLY — this is the one stage that's genuinely parallelizable (unlike the
        # dependent plan→build→review chain below). A single focused topic stays one pass.
        questions = _split_research(task, budget) if MAX_PARALLEL_FANOUT > 1 else []
        base_prompt = ("Research ONLY what's needed to inform the work below, and produce a "
                       "concise, cited findings summary another engineer can act on. Do NOT "
                       "write the final code/deliverable — just the findings.\n\nGOAL:\n" + task)
        if len(questions) > 1:
            model = registry.model_for_tier("tier2", task_type="research")
            for idx, q in enumerate(questions, 1):
                _emit({"type": "assign", "agent": "research", "label": "Research", "model": model,
                       "subtask": q, "reason": f"parallel research {idx}/{len(questions)}",
                       "step": idx, "stage": "research"})
            specs = [{"agent": "research", "task_type": "research",
                      "instruction": ("Research THIS specific question and return a concise, cited "
                                      "findings summary another engineer can act on (no final "
                                      "code/deliverable):\n" + q +
                                      "\n\nOVERALL GOAL (context only):\n" + task)}
                     for q in questions]
            pairs = _run_agents_parallel(specs, budget, emit, approve)
            for idx, (aid, r) in enumerate(pairs):
                board.post("research", f"findings-{idx + 1}", f"Q: {questions[idx]}\n{r}")
            findings = "\n\n".join(f"### {questions[idx]}\n{r}" for idx, (aid, r) in enumerate(pairs))
        else:
            _assign("research", "research", "tier2", "research", "pipeline: gather the inputs")
            findings = _do_subtask("research", base_prompt, budget, emit, approve, "", False,
                                   task_type="research")
            board.post("research", "findings", findings)
        i += 1
        _plan(i)

    # STAGE 2 — PLAN (the architect reads the real project + the findings, writes design.md)
    _assign("architect", "plan", "tier3", "planning", "pipeline: design the plan")
    pprompt = ("A MAP of the repo is in your context. Use it to open ONLY the files you need "
               "(don't read everything), then turn the goal into a concrete, ordered "
               "implementation plan of small, independently-verifiable steps (each with an "
               "acceptance check) that the coder will follow. Use any research findings in your "
               "context. Respect the existing architecture and style. Write the plan to "
               "design.md.\n\nGOAL:\n" + task
               + (("\n\nACCEPTANCE:\n" + acceptance) if acceptance else ""))
    plan = _do_subtask("architect", pprompt, budget, emit, approve, _map_ctx + board.digest(),
                       False, task_type="planning")
    board.post("architect", "plan", plan)
    i += 1
    _plan(i)

    # STAGE 3 — IMPLEMENT (a single specialist that self-verifies in the sandbox)
    impl_tier = getattr(team.agents.get(impl_agent), "tier", "tier2")
    _assign(impl_agent, "implement", impl_tier, task_type, "pipeline: build it from the plan")
    iprompt = ("Implement the goal by FOLLOWING the ordered plan in your context (from the "
               "architect — also saved as design.md) and using any research findings. Match "
               "the existing architecture, tests, and style. Then run the tests and make sure "
               "everything passes.\n\nGOAL:\n" + task)
    # Critic QA only when we CAN'T self-verify in a sandbox (mirrors the tier-2 gating); when
    # we can, the dedicated code-review stage below covers it — no double review.
    impl_review = bool(review) and not (can_run and os.environ.get("AGENT_BASH_DOCKER_IMAGE", "").strip())
    result = _do_subtask(impl_agent, iprompt, budget, emit, approve, _map_ctx + board.digest(),
                         impl_review, task_type=task_type, acceptance=acceptance,
                         verify_run=can_run, max_rounds=24, stream=True)
    board.post(impl_agent, "implementation", result)
    i += 1
    _plan(i)

    # STAGE 4 — CODE REVIEW (deep review on real code changes; fixes Critical/Major itself)
    if review and can_run:
        _assign("code-reviewer", "review", "tier2", "review", "pipeline: review the change")
        vprompt = ("Review the code changes just made for correctness, security, and quality, "
                   "and RUN the tests. Report a short prioritized list; if you find a Critical "
                   "or Major issue, fix it directly and re-run the tests.\n\nGOAL:\n" + task)
        _do_subtask("code-reviewer", vprompt, budget, emit, approve, board.digest(), False,
                    task_type="review", verify_run=True, max_rounds=12)
        i += 1
        _plan(i)

    _emit({"type": "final", "text": result, "cost": round(budget.spent_usd, 4)})
    return result


# ---- entry point ------------------------------------------------------------
def handle_task(task: str, budget: Budget = None, emit=None, approve=None,
                plan_only=False, subtasks=None, review="auto", parallel=False, stream=False,
                acceptance="", model_override="") -> str:
    budget = budget or Budget()
    # A user-pinned model for this run (composer "Model" picker). Bound as a ContextVar so
    # every registry.model_chain resolution on this run prefers it, with routing as fallback;
    # concurrent runs/sessions keep their own. Cleared automatically when None/"".
    registry.set_model_override(model_override or None)
    # Bind the run budget so tool-internal model calls (see_image / safety_check /
    # generate_image) charge THIS run's budget + the daily cap, not a throwaway one.
    # Each run executes on a fresh thread (WS spawns one per turn) or rebinds here before
    # any model call, so we don't need to reset it on this thread.
    set_run_budget(budget)

    def _emit(ev):
        if emit:
            emit(ev)

    # Resume an approved plan -> run the master loop seeded with those todos.
    if subtasks:
        todos = [{"text": s, "status": "pending"} for s in subtasks]
        # Approved multi-step plans are substantive -> QA on unless explicitly disabled.
        rv = review if isinstance(review, bool) else True
        final = _master_loop(task or "Execute the approved plan.", budget, emit, approve, rv,
                             todos, acceptance=acceptance, stream=stream)
        _emit({"type": "final", "text": final, "cost": round(budget.spent_usd, 4)})
        return final

    # Fast-path: obvious chit-chat skips the LLM classifier entirely and is
    # answered by the tool-less `general` agent (one call, cannot loop). This
    # both saves the routing calls and prevents a rate-limited classifier from
    # misrouting a greeting into a tool-spin.
    if not plan_only and _is_trivial_chat(_user_request(task)):
        tier1_model = registry.model_for_tier("tier1")
        _emit({"type": "route", "tier": 1, "task_type": "chat", "requires_web": False,
               "reason": "trivial chat (fast-path)", "routed_model": tier1_model})
        _emit({"type": "assign", "agent": "general", "label": "General Assistant",
               "model": tier1_model, "reason": "trivial chat (fast-path)"})
        # Direct tier-1 call — no agent machinery, no tools, single cheap call.
        chain = registry.model_chain("tier1", task_type="chat")
        try:
            resp, _ = complete_chain(
                chain,
                [{"role": "system", "content": "You are a friendly, concise assistant. Reply in 1-3 sentences."},
                 {"role": "user", "content": _user_request(task)}],
                max_tokens=256, budget=budget, temperature=0.7,
            )
            result = resp.choices[0].message.content or "Hello! How can I help you?"
        except Exception:
            result = "Hello! How can I help you?"
        _emit({"type": "final", "text": result, "cost": round(budget.spent_usd, 4)})
        return result

    # Route on the RAW user request, not the assembled history/memory/project context
    # (which bloats the classifier prompt and can distort the tier — a trivial follow-up
    # buried under pages of context can look "hard"). The agents still receive the full
    # `task`; only the cheap classifier sees the trimmed message.
    cls = classify(_user_request(task), budget=budget)
    tier = cls.get("tier", 2)
    task_type = cls.get("task_type")
    req = _user_request(task)
    # Read/understand an EXISTING shared repo -> force a single agent that can FETCH it
    # (repo-engineer clones + reads), NOT the build path. Prevents the classifier mis-tiering
    # it into a coder/frontend build that never reads the source and hallucinates a summary.
    _ru_agent = _repo_understanding_agent(req)
    if _ru_agent:
        tier, task_type = 2, "research"
        cls = {**cls, "tier": tier, "task_type": task_type,
               "reason": (str(cls.get("reason", "")) + " · read/understand a shared repo → "
                          + _ru_agent).strip(" ·")}
    # Blended difficulty: the classifier is one cheap model's snap judgment and under-tiers big
    # builds. Deterministic scope signals RAISE the tier so the strong-model floor (tier 3 -> a
    # frontier model, not flash) kicks in for genuinely complex build work.
    if task_type in ("coding", "frontend", "data") and tier < 3 and _difficulty_score(req) >= 5:
        tier = 3
        cls = {**cls, "tier": tier,
               "reason": (str(cls.get("reason", "")) + " · complex build → tier 3 (strong model)").strip(" ·")}
    # DEFAULT = a single agent in one tight Claude-Code-style loop (one shared context, full
    # tools). Escalate to the LEAD master loop — which delegates and runs INDEPENDENT steps
    # concurrently via delegate_parallel — ONLY when the task genuinely needs coordination:
    #   * explicit independent multi-part WORK (parallelizable), or
    #   * genuine external-research + build (research agent + coder must cooperate), or
    #   * explicit cross-domain coordination (>=2 domains).
    # Dependent single-domain work (incl. normal coding) stays a single agent — A/B-proven
    # faster + more correct than fragmenting it across a delegated relay.
    if _wants_parallel(req) and any(p.search(req) for p in _DOMAIN_PATS.values()):
        esc_reason = "independent parts → parallel LEAD"
    elif _wants_pipeline(req):
        esc_reason = "research+build → LEAD"
    elif _wants_delegation(req):
        esc_reason = "multi-domain → LEAD"
    else:
        esc_reason = ""
    if esc_reason and not _ru_agent:
        tier = 3
        if task_type in _TIER3_SINGLE_AGENT_TYPES:
            task_type = "general"      # force the LEAD path (a single build agent can't coordinate/parallelize)
        cls = {**cls, "tier": tier, "task_type": task_type,
               "reason": (str(cls.get("reason", "")) + " · " + esc_reason).strip(" ·")}
    _emit({**cls, "type": "route"})
    review = _resolve_review(review, tier, task_type)

    # Plan-first preview.
    if plan_only:
        plan = _make_plan(task, budget) if tier >= 3 else [task]
        _emit({"type": "plan", "subtasks": plan, "plan_only": True,
               "todos": [{"text": s, "status": "pending"} for s in plan]})
        text = ("**Proposed plan**\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(plan, 1)) +
                "\n\n_Approve to run it._")
        _emit({"type": "final", "text": text, "cost": round(budget.spent_usd, 4)})
        return text

    # Simple / moderate -> one focused specialist (its own tool loop is Claude-like).
    if tier < 3:
        if _ru_agent:
            agent_id, reason = _ru_agent, "read/understand a shared repo (deterministic route)"
        else:
            agent_id, reason = team.select_agent(task, budget=budget)
        agent = team.agents.get(agent_id)
        # A BUILD task must go to an agent that can actually edit + run code. The dispatcher
        # (especially its keyword fallback when the LLM pick fails) sometimes hands a coding/UI
        # build to research/doc/general — which have no run_bash and just narrate or flail
        # (observed live: a "host my calculator" request went to research, which wrote a Flask
        # app it never ran). Repin such tasks to the right builder.
        if (not _ru_agent and (task_type in ("coding", "frontend", "data") or _produces_file(req))
                and not {"edit_file", "run_bash"}.issubset(set(getattr(agent, "tools", None) or []))):
            _want = "frontend" if task_type == "frontend" else "coder"
            _repl = team.agents.get(_want)
            if _repl and {"edit_file", "run_bash"}.issubset(set(_repl.tools or [])):
                agent_id, agent = _want, _repl
                reason = f"repinned to {_want}: the picked agent can't build+run"
        # #4: a trivial task handed to a TOOL-LESS chat agent (general) can run on the
        # cheaper routed-tier model. But NEVER downgrade a TOOL-USING agent (research,
        # coder, …): they need a capable model for reliable tool-calling — downgrading
        # research to a cheap tier-1 model made it emit XML tool calls as raw text and
        # break the answer (regression). Tool-using agents keep their declared tier.
        downgrade_tier = tier if not getattr(agent, "tools", None) else None
        eff_tier = team._effective_tier(getattr(agent, "tier", "tier2"), downgrade_tier)
        _emit({"type": "assign", "agent": agent_id, "label": getattr(agent, "label", agent_id),
               "model": registry.model_for_tier(eff_tier, task_type=task_type),
               "reason": reason})
        # Tier-2 single-agent runs follow a compact version of the same playbook path
        # (injected into the prompt — no extra calls). Tier-1 trivial work stays lean.
        agent_task = task
        if tier >= 2:
            cl = playbook_lib.checklist(task_type)
            if cl:
                agent_task = f"{task}\n\n{cl}"
        if acceptance:
            agent_task += ("\n\nACCEPTANCE CRITERIA (the definition of done — make sure your "
                           "result satisfies ALL of these):\n" + acceptance)
        # #5: trivial tier-1 work skips auto skill-matching so a one-line factual
        # question can't drag in a heavy skill (e.g. the research report).
        # Verification gate also covers tier-2 coding/data (not just the tier-3 build path):
        # a moderate "write X and run it" task must still actually execute, or be flagged
        # UNVERIFIED — otherwise it relies on the model choosing to be honest (testing showed
        # a complex build routed tier-2 and the gate didn't arm).
        _verify = tier >= 2 and ((task_type or "") in ("coding", "data") or _produces_file(req))
        result = _do_subtask(agent_id, agent_task, budget, emit, approve, "", review, stream,
                             task_type=task_type, acceptance=acceptance, tier=downgrade_tier,
                             use_skills=(tier >= 2),
                             verify_run=_verify, max_rounds=(22 if _verify else None))
        _emit({"type": "final", "text": result, "cost": round(budget.spent_usd, 4)})
        return result

    # Complex CODING/build -> a SINGLE strong agent in one tight loop (Claude-Code/OpenCode
    # style), NOT the multi-agent decomposition: for dependent builds it's far faster and
    # actually produces working code (see _TIER3_SINGLE_AGENT_TYPES). No tier downgrade —
    # the agent keeps its capable model, and gets the full tier-3 budget/round headroom.
    if task_type in _TIER3_SINGLE_AGENT_TYPES:
        # Phased build (default): STRONG model plans -> cheap flash implements the plan ->
        # STRONG model reviews -> flash fixes; a stuck implement escalates to the strong model.
        # Cost-effective quality for complex builds. AGENT_PHASED_BUILD=0 uses the single
        # strong-agent path below instead (kept for A/B comparison).
        if os.environ.get("AGENT_PHASED_BUILD", "1").strip().lower() in ("1", "true", "yes"):
            final = _phased_build(task, budget, emit, approve, review, task_type,
                                  acceptance=acceptance, stream=stream)
            _emit({"type": "final", "text": final, "cost": round(budget.spent_usd, 4)})
            return final
        agent_id, reason = team.select_agent(task, budget=budget)
        agent = team.agents.get(agent_id)
        # The build agent MUST be able to build AND verify (edit + execute). The
        # dispatcher sometimes picks a non-building specialist for a big build (live
        # test 2026-07: `architect` — no edit_file/run_bash — flailed for 18 writes and
        # finished UNVERIFIED). Keep a capable pick (coder/frontend/fast-coder); anything
        # that can't edit+run is repinned to `coder`.
        _need = {"edit_file", "run_bash"}
        if not (agent and _need.issubset(set(agent.tools or []))):
            fallback = team.agents.get("coder")
            if fallback and _need.issubset(set(fallback.tools or [])):
                agent_id, reason = "coder", f"repinned: {agent_id} can't build+verify"
                agent = fallback
        _emit({"type": "assign", "agent": agent_id, "label": getattr(agent, "label", agent_id),
               "model": registry.model_for_tier(getattr(agent, "tier", "tier3"), task_type=task_type),
               "reason": reason})
        agent_task = task
        cl = playbook_lib.checklist(task_type)
        if cl:
            agent_task = f"{task}\n\n{cl}"
        if acceptance:
            agent_task += ("\n\nACCEPTANCE CRITERIA (the definition of done — make sure your "
                           "result satisfies ALL of these):\n" + acceptance)
        # This is a SINGLE self-verifying agent (it runs the tests in the sandbox in its
        # own loop), so apply the SAME sandbox-aware critic gating as tier-2 instead of
        # tier-3's blanket always-review — a second full critic pass here is redundant and
        # roughly doubled the wall-clock in testing (7.3 min vs 3.2 min). Critic still runs
        # when forced (AGENT_ALWAYS_REVIEW) or when no sandbox is available to self-verify.
        build_review = review and (
            os.environ.get("AGENT_ALWAYS_REVIEW", "").strip().lower() in ("1", "true", "yes")
            or not os.environ.get("AGENT_BASH_DOCKER_IMAGE", "").strip())
        # Force STREAMING for the build agent (regardless of the caller's `stream`): on the
        # free tier these models take ~70s/call but stream smoothly (probe 2026-06-22: max
        # inter-token gap ≤13s). Streaming routes through the PER-CHUNK wall-clock watchdog
        # (llm._iter_stream_bounded) which only trips on a true stall — instead of the flat
        # 45s total wall-clock that was guillotining actively-streaming calls (~3 min/run of
        # spurious timeout fallbacks). Live `agent_token` events are a bonus for the UI.
        result = _do_subtask(agent_id, agent_task, budget, emit, approve, "", build_review, True,
                             task_type=task_type, acceptance=acceptance, tier=None, use_skills=True,
                             verify_run=True, max_rounds=22)
        _emit({"type": "final", "text": result, "cost": round(budget.spent_usd, 4)})
        return result

    # Complex (non-coding) -> the LEAD master loop, seeded with the task's playbook + delegation.
    final = _master_loop(task, budget, emit, approve, review, task_type=task_type,
                         acceptance=acceptance, stream=stream)
    _emit({"type": "final", "text": final, "cost": round(budget.spent_usd, 4)})
    return final
