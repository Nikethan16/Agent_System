"""
agent.py — the agent loop (think -> act -> observe), now data-driven.

Generalized from the original single worker loop so ANY agent can run with:
  * its own system prompt + model,
  * a least-privilege subset of tools (resolved from the tool registry by name),
  * an optional approval gate for risky actions.

Still provider-agnostic (speaks the OpenAI tool-calling format that LiteLLM
normalizes) and still budget-capped. The security gate is deterministic
(core/policy.py); escalations are handed to the injected `approve` callback —
no UI or provider code enters core.
"""
import os
import re
import json

from .llm import complete, complete_chain, stream_complete_tools, Budget, BudgetExceeded
from .registry import registry
from . import toolbelt
from . import policy

# --- within-run context compaction (phase 2 — root fix for orchestration #2) -
# A long task's message history grows until it hits the iteration/context cap and
# returns raw text. Instead, when the running history gets large we summarize the
# OLDER middle turns into one note and keep the system prompt + recent turns. We
# never split an assistant's tool_calls from its tool results (that would make the
# message list invalid for the provider). Best-effort: a compaction failure never
# breaks the run. Toggle with AGENT_COMPACT=0.
_COMPACT_KEEP = int(os.environ.get("AGENT_COMPACT_KEEP", "6"))      # recent msgs kept verbatim
_COMPACT_RATIO = float(os.environ.get("AGENT_COMPACT_RATIO", "0.8"))  # of the context budget

# Structured "anchored summary" template for compaction (design adapted from OpenCode's
# session compaction — see THIRD_PARTY.md; reimplemented as our own prompt). A fixed
# section layout preserves the things a long build must not forget — goal, constraints,
# what's done vs left, key decisions, and exact file paths/commands/errors — far better
# than a free-form summary, so the agent can resume cleanly after older turns are dropped.
_COMPACT_SUMMARY_SYS = (
    "You are compacting an agent work-log so the task can continue after older turns are "
    "dropped. Output EXACTLY this Markdown structure, every section kept (use '(none)' when "
    "empty), terse bullets not prose. Preserve exact file paths, commands, error strings, and "
    "identifiers verbatim. Do not mention that the context was compacted.\n\n"
    "## Goal\n- [one-sentence task summary]\n\n"
    "## Constraints & Preferences\n- [requirements/specs or (none)]\n\n"
    "## Progress\n### Done\n- [completed work or (none)]\n### In Progress\n- [current work or (none)]\n"
    "### Blocked\n- [blockers or (none)]\n\n"
    "## Key Decisions\n- [decision and why, or (none)]\n\n"
    "## Next Steps\n- [ordered next actions or (none)]\n\n"
    "## Critical Context\n- [important technical facts, errors, open questions, or (none)]\n\n"
    "## Relevant Files\n- [path: why it matters, or (none)]"
)


def _approx_tokens(messages) -> int:
    total = 0
    for m in messages:
        c = m.get("content")
        total += len(c) if isinstance(c, str) else (len(str(c)) if c else 0)
        if m.get("tool_calls"):
            total += len(str(m["tool_calls"]))
    return total // 4


def _compact_messages(messages, budget=None, emit=None, label="agent"):
    """Summarize older turns when the history is large; keep system + recent turns.
    Returns the (possibly) shortened message list. Never raises."""
    if os.environ.get("AGENT_COMPACT", "").strip().lower() in ("0", "false", "no"):
        return messages
    try:
        budget_tokens = registry.context_budget()
    except Exception:
        budget_tokens = 24000
    if not budget_tokens or budget_tokens <= 0:
        return messages
    threshold = int(budget_tokens * _COMPACT_RATIO)
    if _approx_tokens(messages) <= threshold or len(messages) <= _COMPACT_KEEP + 2:
        return messages

    head = messages[:1]                       # the system prompt
    keep_from = max(1, len(messages) - _COMPACT_KEEP)
    # The kept tail must NOT start on a 'tool' message (it has to follow its
    # assistant's tool_calls) — advance until it starts on a non-tool message.
    while keep_from < len(messages) and messages[keep_from].get("role") == "tool":
        keep_from += 1
    middle, tail = messages[1:keep_from], messages[keep_from:]
    if not middle:
        return messages

    lines = []
    for m in middle:
        content = m.get("content") or ""
        if m.get("tool_calls"):
            names = ", ".join(tc.get("function", {}).get("name", "")
                              for tc in m["tool_calls"] if isinstance(tc, dict))
            content = f"{content} [called: {names}]"
        lines.append(f"{m.get('role', '?')}: {str(content)[:1000]}")
    convo = "\n".join(lines)[:12000]
    try:
        # Use the fallback CHAIN, not a single model: compaction is needed most when a
        # long run is under provider pressure — a single rate-limited model would make
        # _compact_messages silently no-op exactly when it matters.
        chain = registry.model_chain("tier1")
        resp, _ = complete_chain(
            chain,
            [{"role": "system", "content": _COMPACT_SUMMARY_SYS},
             {"role": "user", "content": convo}],
            max_tokens=700, budget=budget, temperature=0.2)
        summary = (resp.choices[0].message.content or "").strip()
    except Exception:
        return messages          # budget/provider issue — leave history as-is
    if not summary:
        return messages
    if emit:
        emit({"type": "thought", "agent": label,
              "text": "(compacted earlier context to stay within the window)"})
    return head + [{"role": "user",
                    "content": "[Summary of earlier work in this task]\n" + summary}] + tail

# --- leaked-tool-call detection (orchestration issue #1) --------------------
# Cheap models (DeepSeek/Qwen seen in live traces) sometimes emit a tool call as
# PLAIN TEXT instead of a structured tool_call — e.g. "<｜DSML｜tool_calls>" or
# "<tool_call><function=run_bash>". That raw markup must never be surfaced as the
# user-facing final answer. Mirrors OpenCode routing malformed calls to `invalid`.
#
# Vendor "special tokens" use full-width pipes + 'tool_calls' and never occur in
# legitimate prose -> conclusive. A generic <tool_call>/<function=> tag counts
# ONLY when the message STARTS with it (the model is emitting a call), so a normal
# answer that merely quotes such syntax (in a sentence or a code block) passes
# through untouched.
_RAW_TOOLCALL_SPECIAL = re.compile(r"<｜[^｜>]*tool[_ ]?calls?[^｜>]*｜?>|<｜DSML｜>")


def _looks_like_raw_toolcall(text: str) -> bool:
    """True when `text` is a model EMITTING a tool call as content (must not be
    shown as a final answer). The caller must already have confirmed there are NO
    structured tool_calls on the message."""
    if not text:
        return False
    if _RAW_TOOLCALL_SPECIAL.search(text):
        return True
    head = text.lstrip()[:40].lower()
    return head.startswith(("<tool_call", "<function=", "<｜"))


# Patterns to strip from a final answer as a LAST RESORT, so leaked tool-call markup
# never reaches the user even if a model keeps emitting it after the repair re-prompt.
_STRIP_PATTERNS = re.compile(
    r"<｜[^｜>]*｜>|</?tool_call>|<function\s*=[^>]*>|</function>|<arg[^>]*>|</arg>",
    re.IGNORECASE)


def _strip_toolcall_markup(text: str) -> str:
    """Remove tool-call markup tokens from `text`. Used only on a final answer that
    still looked like a raw tool call after the one-shot repair."""
    return _STRIP_PATTERNS.sub("", text or "").strip()

# After this many tool-using rounds, force a final (no-tools) answer so a weaker
# model can't spin on tool calls forever. Raised from 8 so real coding work
# (explore → edit → run tests → fix → re-run) has room to finish; the per-run
# Budget is still the hard global ceiling. Tunable via env.
MAX_TOOL_ROUNDS = int(os.environ.get("AGENT_MAX_TOOL_ROUNDS", "14"))

# Forcing prompt injected when the tool-round cap is hit (tools are also dropped from the
# request). A firm, structured instruction yields a clean text summary instead of the model
# trying (and failing) to keep calling now-absent tools. Adapted from OpenCode's
# MAX_STEPS_PROMPT (see THIRD_PARTY.md); our own wording.
_MAX_STEPS_PROMPT = (
    "MAXIMUM STEPS REACHED — tools are now disabled for this task. Respond with TEXT ONLY, "
    "no tool calls of any kind. Give the FINAL answer: summarize what you accomplished, list "
    "anything still incomplete, and include the key results (files written, how to run/verify "
    "them). This instruction overrides any earlier request to keep using tools.")


class _TC:
    """Adapter so a streamed tool-call dict looks like the object form downstream."""
    def __init__(self, d):
        self.id = d["id"]
        self.function = type("F", (), {"name": d["function"]["name"],
                                       "arguments": d["function"]["arguments"]})()


class _StreamMsg:
    def __init__(self, d):
        self.content = d.get("content")
        self._d = d
        self.tool_calls = [_TC(tc) for tc in d.get("tool_calls", [])] or None

    def model_dump(self):
        return self._d


def run_agent(task, system, model, max_tokens=4096, budget: Budget = None,
              label="agent", emit=None, allowed_tools=None, approve=None, stream=False,
              models=None):
    """
    allowed_tools: list of tool names this agent may use (None = all registered).
    approve(tool, args, decision) -> (allowed: bool, reason: str): called only for
        escalated (critical / requires-human) actions. None = auto-approve them.
    stream=True: stream this agent's tokens as `agent_token` events (opt-in).
    models: the ordered fallback chain (primary first). Defaults to [model]. If a
        model is rate-limited across its keys / down, the loop falls back down the
        chain and emits a `fallback` event.
    """
    budget = budget or Budget()
    chain = [m for m in (models or [model]) if m] or [model]

    def _emit(ev):
        if emit:
            emit(ev)

    def _on_fb(frm, to, why):
        _emit({"type": "fallback", "agent": label, "from": frm, "to": to, "reason": why})

    names = allowed_tools if allowed_tools is not None else toolbelt.names()
    schemas = toolbelt.schemas_for(names)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]

    rounds = 0
    nudged = False
    raw_repaired = False   # one-shot guard for leaked-raw-tool-call repair (#1)
    seen_calls = {}        # tool-call signature -> count (stuck/loop detection, G4)
    denied_sigs = {}       # tool-call signature -> denial reason (denial-spin guard)
    loop_break = False
    while True:
        # Loop guard: after too many tool rounds (or a detected stuck loop), drop tools
        # so the model MUST produce a final answer. Prevents weaker models spinning.
        force_final = rounds >= MAX_TOOL_ROUNDS or loop_break
        active_tools = None if force_final else (schemas or None)
        # Compact older turns if the history has grown large (root fix for #2).
        messages = _compact_messages(messages, budget=budget, emit=emit, label=label)
        if force_final and not nudged:
            messages.append({"role": "user", "content": _MAX_STEPS_PROMPT})
            nudged = True
        try:
            if stream:
                try:
                    md, _ = stream_complete_tools(
                        chain[0], messages, tools=active_tools,
                        max_tokens=max_tokens, budget=budget,
                        on_token=lambda t: _emit({"type": "agent_token", "agent": label, "text": t}),
                    )
                    msg = _StreamMsg(md)
                except BudgetExceeded:
                    raise
                except Exception:
                    # Streaming the primary failed — fall back down the chain (non-stream).
                    resp, _ = complete_chain(chain, messages, tools=active_tools,
                                             max_tokens=max_tokens, budget=budget, on_fallback=_on_fb)
                    msg = resp.choices[0].message
            else:
                resp, _ = complete_chain(
                    chain, messages, tools=active_tools,
                    max_tokens=max_tokens, budget=budget, on_fallback=_on_fb,
                )
                msg = resp.choices[0].message
        except BudgetExceeded as e:
            _emit({"type": "limit", "agent": label, "text": str(e)})
            return f"(stopped: {e})"
        except Exception as e:
            # e.g. a provider rate-limit/timeout that survived retries — don't crash
            # the whole turn; surface it and return what we can.
            _emit({"type": "error", "agent": label, "text": f"{type(e).__name__}: {e}"})
            return (f"(The model provider returned an error: {type(e).__name__}. "
                    "This is often a free-tier rate limit — wait a moment and try again.)")

        messages.append(msg.model_dump() if hasattr(msg, "model_dump") else dict(msg))

        if msg.content:
            _emit({"type": "thought", "agent": label, "text": msg.content})

        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            # #1: the model emitted raw tool-call markup as the answer — don't surface
            # it. Re-prompt once for a clean answer / proper call (OpenCode `invalid`).
            if _looks_like_raw_toolcall(msg.content) and not raw_repaired and not force_final:
                raw_repaired = True
                _emit({"type": "retry", "agent": label,
                       "reason": "model emitted a raw tool call as text"})
                messages.append({"role": "user", "content":
                    "Your last message contained raw tool-call markup, not a real tool "
                    "call or a clean answer. If you need a tool, issue it properly; "
                    "otherwise reply with the final answer containing NO tool-call syntax."})
                continue
            # Last resort: the model STILL emitted markup after the repair — strip it so
            # the user never sees literal <tool_call>/<function=> garbage as the answer.
            out = msg.content or ""
            if _looks_like_raw_toolcall(out):
                cleaned = _strip_toolcall_markup(out)
                out = cleaned or ("(I couldn't format a clean answer this time — "
                                  "please try again.)")
            _emit({"type": "done", "agent": label, "text": out})
            return out

        for tc in tool_calls:
            name = tc.function.name
            raw_args = tc.function.arguments or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                # G3: malformed tool JSON — ask the model to repair it instead of
                # running with empty args (which would just error).
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": "ERROR: your tool-call arguments were not valid JSON. "
                                            "Re-issue the call with a valid JSON object."})
                continue
            _emit({"type": "tool", "agent": label, "name": name, "args": args})
            # G4: stuck/loop detection — the same call repeated too many times forces a
            # final answer next round (a weak model echoing one tool can't spin forever).
            sig = f"{name}:{raw_args}"
            seen_calls[sig] = seen_calls.get(sig, 0) + 1
            if seen_calls[sig] >= 3:
                loop_break = True

            # G5: denial-spin guard — if this exact call was already denied, short-circuit
            # immediately instead of re-running the gate (the outcome won't change).
            if sig in denied_sigs:
                result = denied_sigs[sig]
                loop_break = True
            else:
                result = _run_one_tool(name, args, label, approve, emit)
                if str(result).startswith("DENIED"):
                    denied_sigs[sig] = str(result)
                    loop_break = True

            messages.append({
                "role": "tool", "tool_call_id": tc.id, "content": str(result),
            })
        rounds += 1


def _run_one_tool(name, args, label, approve, emit):
    """Apply the security gate, then run the tool. Always audited."""
    def _emit(ev):
        if emit:
            emit(ev)

    tool = toolbelt.get(name)
    if tool is None:
        return f"ERROR: unknown tool {name}"

    # Validate arguments against the tool's schema BEFORE the gate or execution.
    # A malformed call is fed back so the model re-issues it (the single biggest
    # reliability lever for cheap models) — it never reaches the policy gate, so
    # validation can only reject, never bypass security.
    arg_err = toolbelt.validate_args(tool, args)
    if arg_err:
        return (f"INVALID_ARGS for {name}: {arg_err}. Re-issue the call with arguments "
                "that match the tool's schema.")

    decision = policy.evaluate(tool, args)

    if decision.action == "block":
        policy.audit({"agent": label, "tool": name, "args": args,
                      "decision": "block", "reason": decision.reason})
        _emit({"type": "blocked", "agent": label, "name": name, "reason": decision.reason})
        return f"DENIED (policy): {decision.reason}"

    if decision.action == "escalate":
        if approve is not None:
            allowed, reason = approve(tool, args, decision)
        else:
            allowed, reason = True, "auto-approved (no approver configured)"
        policy.audit({"agent": label, "tool": name, "args": args,
                      "decision": "allow" if allowed else "deny",
                      "requires_human": decision.requires_human, "reason": reason})
        if not allowed:
            _emit({"type": "denied", "agent": label, "name": name, "reason": reason})
            return f"DENIED by approver: {reason}"
    else:
        policy.audit({"agent": label, "tool": name, "args": args, "decision": "allow"})

    try:
        return tool.func(**args)
    except Exception as e:
        return f"ERROR running {name}: {type(e).__name__}: {e}"
