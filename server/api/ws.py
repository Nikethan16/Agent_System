"""
ws.py — the live run channel (WebSocket).

Client -> server messages:
  {"type":"run", "text": "...", "max_usd": 0.5, "max_iterations": 12}
  {"type":"approval_response", "id": "...", "allowed": true, "reason": "..."}
  {"type":"stop"}
Server -> client: every pipeline event (route/plan/assign/thought/tool/final/...),
  plus {"type":"approval_request",...}, {"type":"run_complete"}, {"type":"error"}.

The agent run is synchronous, so it runs in a worker THREAD; events are bridged to
the async socket via a thread-safe queue. Approvals block the worker thread until the
client answers (ApprovalBroker). Stop is cooperative (trips the budget's iteration cap).
"""
import os
import json
import asyncio
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.llm import Budget
from ..chat import run_turn
from ..approvals import ApprovalBroker
from ..auth import ws_authorized
from .. import runs

router = APIRouter()

# Hard server-side ceilings so a client can never set a runaway budget (the budget
# invariant must hold even against a hostile client). Clamped in the "run" handler.
_MAX_USD_CEILING = float(os.environ.get("AGENT_MAX_USD_CEILING", "5.0"))
_MAX_ITER_CEILING = int(os.environ.get("AGENT_MAX_ITER_CEILING", "60"))


@router.websocket("/api/ws/{session_id}")
async def run_socket(websocket: WebSocket, session_id: str):
    allowed, reason = ws_authorized(websocket)
    if not allowed:
        await websocket.close(code=1008, reason=reason[:120])
        return
    await websocket.accept()
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    state = {"broker": None, "budget": None}

    def emit(ev):
        loop.call_soon_threadsafe(q.put_nowait, ev)

    async def sender():
        while True:
            ev = await q.get()
            if ev is None:
                break
            try:
                await websocket.send_json(ev)
            except Exception:
                break

    sender_task = asyncio.create_task(sender())

    # Reattach: if a run for this session is still in flight (e.g. the browser reloaded),
    # re-surface any pending approval requests so they can be answered here. The waiting
    # worker thread is unblocked by approvals.resolve() regardless of which socket answers.
    try:
        for a in runs.pending_approvals(session_id):
            emit({"type": "approval_request", "id": a["id"], "tool": a["tool"],
                  "args": json.loads(a.get("args") or "{}"), "risk": a.get("risk", ""),
                  "reason": a.get("reason", ""), "manager_reason": a.get("manager_reason", ""),
                  "reattached": True})
        _ar = runs.active_run(session_id)
        if _ar:
            emit({"type": "reattach", "run": _ar})
    except Exception:
        pass

    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")

            if mtype == "run":
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                # Clamp client-supplied caps to server ceilings — never trust the
                # client to bound its own spend.
                try:
                    req_usd = float(msg.get("max_usd", 0.5))
                    req_iter = int(msg.get("max_iterations", 20))
                except (TypeError, ValueError):
                    req_usd, req_iter = 0.5, 20
                budget = Budget(
                    max_usd=max(0.0, min(req_usd, _MAX_USD_CEILING)),
                    max_iterations=max(1, min(req_iter, _MAX_ITER_CEILING)),
                )
                # Persist a run record so the UI can reattach after a reload, and so the
                # broker can store approvals against this run (answerable out-of-band).
                run_id = runs.start_run(session_id, text)
                broker = ApprovalBroker(emit, budget=budget, mode=msg.get("mode", "auto"),
                                        task_context=text, session_id=session_id, run_id=run_id)
                state["broker"], state["budget"] = broker, budget
                plan_first = bool(msg.get("plan_first", False))
                subtasks = msg.get("subtasks") or None
                # review is tri-state: omit -> "auto" (QA substantive tasks); an explicit
                # bool from the UI toggle overrides (force-on / force-off).
                review = bool(msg["review"]) if "review" in msg else "auto"
                parallel = bool(msg.get("parallel", False))
                stream = bool(msg.get("stream", True))
                attachments = msg.get("attachments") or None
                acceptance = (msg.get("acceptance") or "").strip()

                def worker(text=text, budget=budget, broker=broker, run_id=run_id,
                           plan_first=plan_first, subtasks=subtasks, review=review,
                           parallel=parallel, stream=stream, attachments=attachments,
                           acceptance=acceptance):
                    status = "done"
                    try:
                        run_turn(session_id, text, budget=budget, emit=emit,
                                 approve=broker.approve, plan_first=plan_first,
                                 subtasks=subtasks, review=review,
                                 parallel=parallel, stream=stream, attachments=attachments,
                                 acceptance=acceptance)
                    except Exception as e:
                        status = "error"
                        emit({"type": "error", "text": f"{type(e).__name__}: {e}"})
                    finally:
                        runs.finish_run(run_id, status, budget.spent_usd)
                        emit({"type": "run_complete", "cost": round(budget.spent_usd, 6),
                              "tokens": budget.tokens, "iterations": budget.iterations})

                threading.Thread(target=worker, daemon=True).start()

            elif mtype == "approval_response":
                # Resolve through the process-global registry (not just this socket's
                # broker) so an answer works even on a RECONNECTED socket whose own run
                # didn't raise the request.
                from ..approvals import resolve as _resolve_approval
                _resolve_approval(msg.get("id"), msg.get("allowed", False),
                                  msg.get("reason", ""), decided_by="user")

            elif mtype == "stop":
                b = state["budget"]
                if b:
                    b.max_iterations = b.iterations   # next budget.check() raises -> run halts
                    emit({"type": "stopping"})

    except WebSocketDisconnect:
        pass
    finally:
        await q.put(None)
        sender_task.cancel()
