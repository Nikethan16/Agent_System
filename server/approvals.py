"""
approvals.py — security Layers 3-4: the security-manager agent + the human gate.

When the agent loop escalates a risky tool, this broker:
  1) asks the security-manager AGENT to approve/deny (Layer 3), then
  2) if the action requires a human (or you configured ask_human), surfaces an
     Approve/Deny request over the WebSocket and BLOCKS the worker thread until you
     answer (Layer 4).
The worker runs in a thread; we bridge to the async WebSocket with an Event.
"""
import os
import json
import uuid
import threading

from core.llm import complete, Budget
from core.registry import registry
from core.agents import agents as agent_registry

from . import runs

# Process-global registry of pending human approvals: req_id -> the broker waiting on it.
# This is what lets an approval be answered from ANYWHERE in the process (the WS that
# raised it, a different tab via REST, or Telegram) — not just the originating socket.
_GLOBAL_PENDING: dict[str, "ApprovalBroker"] = {}
_GLOBAL_LOCK = threading.Lock()


def resolve(req_id: str, allowed: bool, reason: str = "", decided_by: str = "user") -> bool:
    """Answer a pending approval from any caller (REST / Telegram / WS). Returns True if
    a waiting run was found and unblocked."""
    with _GLOBAL_LOCK:
        broker = _GLOBAL_PENDING.get(req_id)
    if broker is None:
        # No live waiter (e.g. the worker already timed out) — still record the verdict.
        runs.resolve_approval(req_id, "approved" if allowed else "denied", decided_by)
        return False
    return broker.resolve(req_id, allowed, reason, decided_by=decided_by)


# Hard timeout for the manager review LLM call. Short so it never blocks the
# critical path for long; infra failures are flagged as transient (not genuine denials).
_MANAGER_REVIEW_TIMEOUT = float(os.environ.get("AGENT_MANAGER_TIMEOUT", "15"))


def _manager_review(tool, args, task_context, budget):
    """Layer 3 — the security-manager agent gives a binary approve/deny + reason.

    Uses a cheap tier-1 chain with a hard 15s timeout — security triage is a quick
    binary judgment, not a reasoning task. Infra failures (timeout, rate-limit) are
    flagged with an '[infra]' prefix so the caller knows it's transient, not a genuine
    policy decision, and the agent doesn't spin retrying an unchangeable outcome.
    """
    mgr = agent_registry.get("security-manager")
    if mgr is None:
        return True, "no manager configured"
    # Use cheap + fast tier-1 chain — security triage doesn't need a frontier model.
    from core.llm import complete_chain as _chain
    chain = registry.model_chain("tier1", task_type="classify")
    prompt = (
        f"TASK CONTEXT:\n{task_context or '(none)'}\n\n"
        f"PROPOSED ACTION:\n  tool: {tool.name} (risk={tool.risk})\n"
        f"  args: {json.dumps(args, default=str)}\n\n"
        'Approve only if justified, scoped, and acceptable. Output ONLY JSON: '
        '{"approve": true|false, "reason": "<=20 words"}'
    )
    try:
        resp, _ = _chain(
            chain,
            [{"role": "system", "content": mgr.prompt},
             {"role": "user", "content": prompt}],
            max_tokens=80, budget=budget, temperature=0,
            timeout=_MANAGER_REVIEW_TIMEOUT,
        )
        txt = (resp.choices[0].message.content or "").strip()
        data = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        return bool(data.get("approve")), data.get("reason", "")
    except Exception as e:
        # Infra failure (timeout, rate-limit) — fail closed but flag as transient so
        # the agent knows a retry won't change the outcome and stops spinning.
        return False, f"[infra] manager unavailable: {type(e).__name__}"


class ApprovalBroker:
    """One per run. `emit` pushes events to the client; `resolve` is called by the ws
    when the human answers."""

    def __init__(self, emit, budget: Budget = None, mode: str = "auto",
                 task_context: str = "", timeout: float = 300.0,
                 session_id: str = "", run_id: str = ""):
        # mode: "auto"    -> manager agent + human only for require-human actions
        #       "careful" -> manager agent + human for EVERY escalated action
        #       "trusted" -> auto-approve everything except hard-blocks (no manager/human)
        self.emit = emit
        self.budget = budget
        self.mode = mode
        self.task_context = task_context
        self.timeout = timeout
        self.session_id = session_id
        self.run_id = run_id
        self._pending: dict[str, dict] = {}

    # called inside the worker thread (this is the core `approve` callback)
    def approve(self, tool, args, decision):
        if self.mode == "trusted":
            return True, "trusted mode (auto-approved)"

        # Layer 3: manager agent — consulted ONLY for genuinely critical/irreversible
        # actions (decision.requires_human) in auto mode. Regular write-risk escalations
        # are decided by the deterministic policy gate (Layer 2) that already ran; no
        # second model needed on the hot path. Careful mode reviews everything.
        needs_manager = self.mode == "careful" or decision.requires_human
        if needs_manager:
            m_ok, m_reason = _manager_review(tool, args, self.task_context, self.budget)
            self.emit({"type": "manager_review", "tool": tool.name,
                       "approved": m_ok, "reason": m_reason})
            if not m_ok:
                return False, f"manager denied: {m_reason}"
        else:
            m_reason = "auto-approved (policy gate passed)"

        # Layer 4: human — always in careful mode, else only when policy requires it
        if self.mode == "careful" or decision.requires_human:
            return self._ask_human(tool, args, decision, m_reason)

        return True, m_reason

    def _ask_human(self, tool, args, decision, manager_reason):
        req_id = uuid.uuid4().hex
        ev = threading.Event()
        self._pending[req_id] = {"event": ev, "result": (False, "no response")}
        # Persist + register globally BEFORE emitting, so an answer that arrives from a
        # different client (reconnect / second tab / Telegram) can always find this waiter.
        try:
            runs.create_approval(req_id, self.session_id, self.run_id, tool.name,
                                 json.dumps(args, default=str), tool.risk,
                                 decision.reason, manager_reason or "")
        except Exception:
            pass
        with _GLOBAL_LOCK:
            _GLOBAL_PENDING[req_id] = self
        self.emit({"type": "approval_request", "id": req_id, "tool": tool.name,
                   "args": args, "risk": tool.risk, "reason": decision.reason,
                   "manager_reason": manager_reason})
        try:
            if not ev.wait(timeout=self.timeout):
                self._pending.pop(req_id, None)
                runs.resolve_approval(req_id, "timeout", "timeout")
                return False, "approval timed out"
            return self._pending.pop(req_id)["result"]
        finally:
            with _GLOBAL_LOCK:
                _GLOBAL_PENDING.pop(req_id, None)

    # called when the client answers — from the WS, OR via the module-level resolve()
    # (REST / Telegram). Idempotent: the first answer wins.
    def resolve(self, req_id, allowed, reason="", decided_by="user"):
        p = self._pending.get(req_id)
        if p:
            p["result"] = (bool(allowed), reason or ("approved by user" if allowed else "denied by user"))
            try:
                runs.resolve_approval(req_id, "approved" if allowed else "denied", decided_by)
            except Exception:
                pass
            p["event"].set()
            return True
        return False
