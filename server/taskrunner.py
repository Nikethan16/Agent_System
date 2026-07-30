"""taskrunner.py — run a SEQUENCE of user tasks one-by-one, VERIFYING each before the next.

When a message is an explicit ordered list (numbered or bulleted, >=2 items), each item is
executed as its own pipeline run, in order, in the same chat workspace — carrying context
forward and emitting a `program` progress event (a checklist + done/total counts) after each
step. The per-task runs emit their normal events, so the UI shows BOTH the checklist and the
per-step detail. Progress is persisted automatically (every event is stored), so reloading the
chat shows exactly where the sequence got to.

Per-feature done-gate ("loop engineering"): a feature is not ticked off the instant the agent
stops talking. After each feature runs, it is EVALUATED with the engine's existing checks
(core.orchestrator.evaluate_feature = the act-gate + the deterministic pytest gate + the QA
critic). If it fails, the exact reason is fed back and the feature is re-driven — up to
_MAX_ATTEMPTS total (1 build + 2 re-tries). Only a feature that passes becomes `verified`; one
that's still failing after its re-tries is flagged `needs_attention` (never a false "done") and
the run CONTINUES to the next feature, so one hard feature can't block the rest.

One Budget is shared across all tasks, so a sequence can never spend past the run cap
(invariant #3): if the budget is exhausted mid-way, the remaining tasks are marked skipped and
the run stops with an honest summary.
"""
import re

# A message becomes a "task program" only when it is an EXPLICIT list — a numbered list
# (`1.` / `2)`) or a bulleted list (`- ` / `* ` / `• `) of >=2 items. Ordinary prose (even a
# multi-sentence request) never triggers sequential mode, so this can't surprise a normal turn.
_NUM = re.compile(r"^\s*(\d+)[.)]\s+(.+)$")
_BUL = re.compile(r"^\s*[-*•]\s+(.+)$")
_MAX_TASKS = 20

# Per feature: 1 initial build + 2 re-tries (the owner's "balanced" choice). Each re-try
# re-drives handle_task with the concrete failure feedback, then re-runs the same gate.
_MAX_ATTEMPTS = 3


def parse_tasks(text: str) -> list:
    """Split a message into an ordered task list — ONLY for an explicit numbered/bulleted
    list of >=2 items. Returns [] otherwise (prose stays a single normal turn)."""
    lines = (text or "").splitlines()
    num = [m.group(2).strip() for ln in lines if (m := _NUM.match(ln)) and m.group(2).strip()]
    bul = [m.group(1).strip() for ln in lines if (m := _BUL.match(ln)) and m.group(1).strip()]
    items = num if len(num) >= 2 else (bul if len(bul) >= 2 else [])
    items = [t for t in items if len(t) >= 3][:_MAX_TASKS]
    return items if len(items) >= 2 else []


def _public(program: list) -> list:
    """The checklist shape sent to the UI (no internal result text). Carries the per-feature
    verification state + how many attempts it took, so the UI can show building/checking/fixing
    and a verified vs needs-attention outcome."""
    return [{"text": p["text"], "status": p["status"], "attempts": p.get("attempts", 0)}
            for p in program]


def run_program(tasks: list, context: str, budget, emit, approve=None, review="auto",
                stream: bool = True, acceptance: str = "", model_override: str = "") -> str:
    """Execute each task in order via the normal pipeline, VERIFYING each before advancing, and
    emitting `program` progress events. Returns a combined summary suitable for storing as the
    assistant's reply."""
    from core.orchestrator import handle_task, evaluate_feature, _workspace_sig
    from core.tools import current_workspace

    program = [{"text": t, "status": "pending", "result": "", "attempts": 0} for t in tasks]
    total = len(program)

    def _progress(current: int):
        emit({"type": "program", "tasks": _public(program), "current": current,
              # `done` counts only VERIFIED features — a flagged/errored one is not "done".
              "done": sum(1 for p in program if p["status"] == "verified"), "total": total})

    def _budget_spent() -> bool:
        return budget is not None and budget.spent_usd >= budget.max_usd

    _progress(0)
    for i, item in enumerate(program):
        # Never spend past the run cap — stop and mark the rest skipped (invariant #3).
        if _budget_spent():
            for p in program[i:]:
                p["status"] = "skipped"
            _progress(i)
            break
        item["status"] = "in_progress"
        _progress(i)
        done_list = "\n".join(f"- {p['text']} (done)" for p in program[:i]) or "(none yet)"

        def _prompt(feedback: str = "") -> str:
            # The feature goes LAST, after a `NEW REQUEST:` marker, so the router judges the FEATURE
            # (via _user_request / _cache_key) — NOT the prepended project context, which otherwise
            # trips the difficulty/delegation escalation and over-routes every step to the tier-3
            # LEAD path (found via dogfooding: a simple "add a function + test" routed multi-domain
            # → LEAD). Retry feedback goes in the framing, before the marker, so it can't skew routing.
            fb = (f"A previous attempt FAILED a check — fix these first, then finish:\n{feedback}\n\n"
                  if feedback else "")
            return (f"{context}\n\n" if context else "") + (
                f"You are working through a sequence of {total} tasks, ONE AT A TIME (this is task "
                f"{i + 1} of {total}). Already completed:\n{done_list}\n\n{fb}"
                "Do ONLY the next task now, fully — actually PERFORM it with your tools (write/edit "
                "files, run commands), don't just describe it; it's done only once the real change "
                "exists (the file is written, the command has run).\n\n"
                f"NEW REQUEST: {item['text']}")

        passed, feedback = False, ""
        try:
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                item["attempts"] = attempt
                _progress(i)  # surfaces "try N" on the checklist during re-work
                prompt = _prompt(feedback if attempt > 1 else "")
                # Snapshot the workspace BEFORE the run so the act-gate can tell if files changed.
                before_sig = _workspace_sig(current_workspace())
                # review=False here: evaluate_feature below is the ONE authoritative QA gate for
                # the feature (avoids a duplicate critic call). The deterministic build-time
                # test gate + act-gate inside handle_task still run — they aren't tied to `review`.
                res = handle_task(prompt, budget=budget, emit=emit, approve=approve,
                                  review=False, stream=stream, acceptance=acceptance,
                                  model_override=model_override)
                item["result"] = (res or "")[:600]
                passed, feedback = evaluate_feature(item["text"], res, before_sig, budget,
                                                    emit=emit, approve=approve, acceptance=acceptance)
                if passed or _budget_spent():
                    break
            item["status"] = "verified" if passed else "needs_attention"
            if not passed:
                # Keep the concrete reason on the record so the summary is honest.
                item["result"] = (f"⚠️ Not verified after {item['attempts']} attempt(s): "
                                  f"{feedback}\n\n{item['result']}")[:800]
        except Exception as e:
            item["status"], item["result"] = "error", f"{type(e).__name__}: {e}"[:300]
        _progress(i + 1)

    return _summary(program)


def _summary(program: list) -> str:
    """An honest scoreboard: only VERIFIED features count as done; flagged/errored ones are
    called out with their reason so the owner knows exactly what to look at."""
    icon = {"verified": "✅", "needs_attention": "⚠️", "error": "❌", "skipped": "⏭️"}
    total = len(program)
    verified = sum(1 for p in program if p["status"] == "verified")
    flagged = [(i, p) for i, p in enumerate(program)
               if p["status"] in ("needs_attention", "error")]

    lines = []
    for i, p in enumerate(program):
        tries = p.get("attempts", 0)
        suffix = f"  (took {tries} attempt{'s' if tries != 1 else ''})" if tries > 1 else ""
        lines.append(f"{icon.get(p['status'], '▫️')} Task {i + 1}: {p['text']}{suffix}")

    head = f"Verified {verified}/{total} features (each built, then checked before the next)."
    if flagged:
        head += (f" {len(flagged)} need{'s' if len(flagged) == 1 else ''} attention — "
                 "see the details below.")

    detail = "\n\n".join(f"**Task {i + 1}: {p['text']}**\n{p['result']}"
                         for i, p in enumerate(program) if p.get("result"))
    return head + "\n\n" + "\n".join(lines) + (("\n\n---\n\n" + detail) if detail else "")
