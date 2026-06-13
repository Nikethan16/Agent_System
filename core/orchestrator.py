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
import json
import re

from .llm import complete, complete_chain, Budget, BudgetExceeded
from .registry import registry
from .router import classify
from . import agents as team
from . import toolbelt
from . import skills as skill_lib
from .agent import _run_one_tool
from .blackboard import Blackboard

MAX_MASTER_ROUNDS = 16     # hard cap on lead loop iterations
MAX_DELEGATIONS = 10       # hard cap on subagent spawns per run (depth-limited too)

# Task types that warrant an automatic QA pass when review is left on "auto":
# substantive *build/analysis* work where a concrete pass/fail check adds value.
# Trivial (tier 1) and pure look-up/chat tasks are skipped to save cost + latency.
_REVIEW_TASK_TYPES = {"coding", "writing", "data", "math"}


def _auto_review(tier, task_type) -> bool:
    """Decide whether to run the critic when review == 'auto' (the default)."""
    if tier >= 3:
        return True
    return tier >= 2 and (task_type in _REVIEW_TASK_TYPES)


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
    "You are the LEAD engineer coordinating a complex task. You work in a loop:\n"
    "1) Call write_todos to lay out a short plan (3-6 concrete steps).\n"
    "2) Work the steps: DELEGATE well-scoped steps to a specialist with the `delegate` "
    "tool, or do small steps yourself with read_file/list_files/write_file/edit_file/run_bash "
    "(read a file before you edit it; use edit_file for precise changes, write_file only "
    "for new files).\n"
    "3) After each step, update the todo statuses with write_todos.\n"
    "4) When ALL steps are done, reply with a concise final answer for the user "
    "(mention any files produced) and DO NOT call any tool in that final message.\n\n"
    "Delegate by capability — coding→coder, web research→research, documents→doc, "
    "UI/HTML→frontend, images→image, QA→critic. Specialists have their own tools; you "
    "coordinate. Keep the plan tight and finish.\n\n"
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


# ---- a single specialist step (with optional QA retry) ---------------------
def _review(task, result, budget, emit, approve):
    def _emit(ev):
        if emit:
            emit(ev)
    prompt = (f"TASK:\n{task}\n\nPRODUCED RESULT:\n{result}\n\n"
              "Inspect the workspace files and run tests if useful, then judge it.")
    raw = team.run("critic", prompt, budget=budget, emit=emit, approve=approve)
    try:
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        passed, issues, summary = bool(data.get("pass")), data.get("issues", []), data.get("summary", "")
    except Exception:
        passed, issues, summary = True, [], "(unparseable verdict)"
    _emit({"type": "critic", "passed": passed, "issues": issues, "summary": summary})
    return passed, summary + ("\n- " + "\n- ".join(issues) if issues else "")


def _do_subtask(agent_id, task, budget, emit, approve, context, review, stream=False, task_type=None):
    r = team.run(agent_id, task, budget=budget, emit=emit, approve=approve,
                 context=context, stream=stream, task_type=task_type)
    if review:
        passed, feedback = _review(task, r, budget, emit, approve)
        if not passed:
            fix = f"{task}\n\nA QA reviewer found issues — fix them:\n{feedback}"
            r = team.run(agent_id, fix, budget=budget, emit=emit, approve=approve,
                         context=context, stream=stream, task_type=task_type)
    return r


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
            "description": "Hand a well-scoped step to a specialist agent; it returns the result.",
            "parameters": obj({"agent": {"type": "string"}, "instruction": {"type": "string"},
                               "skill": {"type": "string",
                                         "description": "Optional skill name to load for this step "
                                                        "(e.g. docx, xlsx, pptx, pdf)."}},
                              ["agent", "instruction"])}},
    ]
    return meta + toolbelt.schemas_for(["read_file", "list_files", "write_file", "edit_file", "run_bash"])


def _master_loop(task, budget, emit, approve, review, initial_todos=None):
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
    if review:
        system += "\n- Before finishing, delegate a QA check to 'critic' and fix anything it flags."

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": task}]

    # Always start from an explicit plan so the breakdown is grounded and visible —
    # the lead then executes/adapts it (this is what makes "break down the task" reliable
    # even when a model wouldn't spontaneously call write_todos).
    todos = list(initial_todos or [])
    if not todos:
        todos = [{"text": s, "status": "pending"} for s in _make_plan(task, budget)]
    _emit({"type": "plan", "subtasks": [t["text"] for t in todos], "todos": todos})
    messages.append({"role": "user",
                     "content": ("Here is the plan. Work through it step by step — delegate each "
                                 "step to the right specialist (or do small steps yourself), update "
                                 "the todos as you go, then give the final answer:\n" + _todos_text(todos))})

    board = Blackboard()
    schemas = _master_tool_schemas()
    rounds, delegations = 0, 0

    while True:
        force_final = rounds >= MAX_MASTER_ROUNDS
        try:
            resp, _ = complete_chain(chain, messages, tools=None if force_final else schemas,
                                     max_tokens=registry.max_tokens_for_tier("tier3"),
                                     budget=budget, on_fallback=_fb)
        except BudgetExceeded as e:
            _emit({"type": "limit", "agent": "lead", "text": str(e)})
            return _finalize_from_board(board, task, budget, emit) or f"(stopped: {e})"
        except Exception as e:
            _emit({"type": "error", "agent": "lead", "text": f"{type(e).__name__}: {e}"})
            return _finalize_from_board(board, task, budget, emit) or f"(provider error: {type(e).__name__})"

        if not getattr(resp, "choices", None):
            # Provider returned NO choices (free-tier rate-limit / safety filter /
            # empty completion). The single-agent loop is already guarded; guard the
            # LEAD loop the same way so a transient empty response can't crash the run.
            _emit({"type": "error", "agent": "lead",
                   "text": "empty response from model (often a free-tier rate limit)"})
            return (_finalize_from_board(board, task, budget, emit) or
                    "(The model returned an empty response — often a free-tier rate "
                    "limit. Wait a moment and try again.)")
        msg = resp.choices[0].message
        messages.append(msg.model_dump() if hasattr(msg, "model_dump") else dict(msg))
        if msg.content:
            _emit({"type": "thought", "agent": "lead", "text": msg.content})

        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return msg.content or _finalize_from_board(board, task, budget, emit)

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if name == "write_todos":
                todos = args.get("todos") or todos
                _emit({"type": "plan", "subtasks": [t.get("text", "") for t in todos], "todos": todos})
                result = "todos updated"
            elif name == "delegate":
                if delegations >= MAX_DELEGATIONS:
                    result = "Delegation limit reached — do the remaining steps yourself or finish."
                else:
                    delegations += 1
                    agent_id = (args.get("agent") or "general").strip()
                    if agent_id not in team.agents.agents:
                        agent_id = team._fallback_select(args.get("instruction", ""))
                    agent = team.agents.get(agent_id)
                    instruction = args.get("instruction") or args.get("task") or ""
                    skill_arg = args.get("skill")
                    skills = [skill_arg] if isinstance(skill_arg, str) and skill_arg.strip() else None
                    _emit({"type": "assign", "agent": agent_id, "label": getattr(agent, "label", agent_id),
                           "model": registry.model_for_tier(getattr(agent, "tier", "tier2")),
                           "subtask": instruction, "reason": "delegated by lead", "step": delegations,
                           "skill": skill_arg or None})
                    result = team.run(agent_id, instruction, budget=budget, emit=emit,
                                      approve=approve, context=board.digest(), skills=skills)
                    board.post(agent_id, f"step-{delegations}", f"{instruction}\n{result}")
            else:
                result = _run_one_tool(name, args, "lead", approve, emit)

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})

        rounds += 1
        # Claude-style reminder injection: keep the live plan in front of the model.
        if todos:
            messages.append({"role": "user", "content": "(reminder) current todo list:\n" + _todos_text(todos)})


def _finalize_from_board(board, task, budget, emit):
    """If the lead ran out of budget mid-flight, synthesize what's on the blackboard."""
    digest = board.digest()
    if not digest:
        return ""
    try:
        model = registry.model_for_tier("tier3")
        resp, _ = complete(model, [
            {"role": "system", "content": "Summarize the work done so far into a final answer for the user."},
            {"role": "user", "content": f"GOAL: {task}\n\nWORK DONE:\n{digest}"}],
            max_tokens=registry.max_tokens_for_tier("tier3"), budget=budget)
        return resp.choices[0].message.content
    except Exception:
        return digest[:1500]


# ---- entry point ------------------------------------------------------------
def handle_task(task: str, budget: Budget = None, emit=None, approve=None,
                plan_only=False, subtasks=None, review="auto", parallel=False, stream=False) -> str:
    budget = budget or Budget()

    def _emit(ev):
        if emit:
            emit(ev)

    # Resume an approved plan -> run the master loop seeded with those todos.
    if subtasks:
        todos = [{"text": s, "status": "pending"} for s in subtasks]
        # Approved multi-step plans are substantive -> QA on unless explicitly disabled.
        rv = review if isinstance(review, bool) else True
        final = _master_loop(task or "Execute the approved plan.", budget, emit, approve, rv, todos)
        _emit({"type": "final", "text": final, "cost": round(budget.spent_usd, 4)})
        return final

    # Fast-path: obvious chit-chat skips the LLM classifier entirely and is
    # answered by the tool-less `general` agent (one call, cannot loop). This
    # both saves the routing calls and prevents a rate-limited classifier from
    # misrouting a greeting into a tool-spin.
    if not plan_only and _is_trivial_chat(_user_request(task)):
        _emit({"type": "route", "tier": 1, "task_type": "chat", "requires_web": False,
               "reason": "trivial chat (fast-path)",
               "routed_model": registry.model_for_tier("tier1")})
        agent = team.agents.get("general")
        _emit({"type": "assign", "agent": "general",
               "label": getattr(agent, "label", "general"),
               "model": registry.model_for_tier(getattr(agent, "tier", "tier2")),
               "reason": "trivial chat (fast-path)"})
        result = _do_subtask("general", task, budget, emit, approve, "", False,
                             stream, task_type="chat")
        _emit({"type": "final", "text": result, "cost": round(budget.spent_usd, 4)})
        return result

    cls = classify(task, budget=budget)
    _emit({**cls, "type": "route"})
    tier = cls.get("tier", 2)
    task_type = cls.get("task_type")
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
        agent_id, reason = team.select_agent(task, budget=budget)
        agent = team.agents.get(agent_id)
        _emit({"type": "assign", "agent": agent_id, "label": getattr(agent, "label", agent_id),
               "model": registry.model_for_tier(getattr(agent, "tier", "tier2"), task_type=task_type),
               "reason": reason})
        result = _do_subtask(agent_id, task, budget, emit, approve, "", review, stream, task_type=task_type)
        _emit({"type": "final", "text": result, "cost": round(budget.spent_usd, 4)})
        return result

    # Complex -> the LEAD master loop with todos + delegation.
    final = _master_loop(task, budget, emit, approve, review)
    _emit({"type": "final", "text": final, "cost": round(budget.spent_usd, 4)})
    return final
