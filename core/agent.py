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
import json

from .llm import complete, complete_chain, stream_complete_tools, Budget, BudgetExceeded
from . import toolbelt
from . import policy

# After this many tool-using rounds, force a final (no-tools) answer so a weaker
# model can't spin on tool calls forever. Raised from 8 so real coding work
# (explore → edit → run tests → fix → re-run) has room to finish; the per-run
# Budget is still the hard global ceiling. Tunable via env.
MAX_TOOL_ROUNDS = int(os.environ.get("AGENT_MAX_TOOL_ROUNDS", "14"))


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
    seen_calls = {}        # tool-call signature -> count (stuck/loop detection, G4)
    denied_sigs = {}       # tool-call signature -> denial reason (denial-spin guard)
    loop_break = False
    while True:
        # Loop guard: after too many tool rounds (or a detected stuck loop), drop tools
        # so the model MUST produce a final answer. Prevents weaker models spinning.
        force_final = rounds >= MAX_TOOL_ROUNDS or loop_break
        active_tools = None if force_final else (schemas or None)
        if force_final and not nudged:
            messages.append({"role": "user",
                             "content": "Enough tool use — give me your final answer now."})
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
            _emit({"type": "done", "agent": label, "text": msg.content or ""})
            return msg.content or ""

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
