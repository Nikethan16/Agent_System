"""taskrunner.py — run a SEQUENCE of user tasks one-by-one with live progress.

When a message is an explicit ordered list (numbered or bulleted, >=2 items), each item is
executed as its own pipeline run, in order, in the same chat workspace — carrying context
forward and emitting a `program` progress event (a checklist + done/total counts) after each
step. The per-task runs emit their normal events, so the UI shows BOTH the checklist and the
per-step detail. Progress is persisted automatically (every event is stored), so reloading the
chat shows exactly where the sequence got to.

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
    """The checklist shape sent to the UI (no internal result text)."""
    return [{"text": p["text"], "status": p["status"]} for p in program]


def run_program(tasks: list, context: str, budget, emit, approve=None, review="auto",
                stream: bool = True, acceptance: str = "", model_override: str = "") -> str:
    """Execute each task in order via the normal pipeline, emitting `program` progress events.
    Returns a combined summary suitable for storing as the assistant's reply."""
    from core.orchestrator import handle_task

    program = [{"text": t, "status": "pending", "result": ""} for t in tasks]
    total = len(program)

    def _progress(current: int):
        emit({"type": "program", "tasks": _public(program), "current": current,
              "done": sum(1 for p in program if p["status"] == "done"), "total": total})

    _progress(0)
    for i, item in enumerate(program):
        # Never spend past the run cap — stop and mark the rest skipped (invariant #3).
        if budget is not None and budget.spent_usd >= budget.max_usd:
            for p in program[i:]:
                p["status"] = "skipped"
            _progress(i)
            break
        item["status"] = "in_progress"
        _progress(i)
        done_list = "\n".join(f"- {p['text']} (done)" for p in program[:i]) or "(none yet)"
        prompt = (f"{context}\n\n" if context else "") + (
            f"You are working through a numbered sequence of {total} tasks, ONE AT A TIME.\n"
            f"Already completed:\n{done_list}\n\n"
            f"NOW COMPLETE ONLY TASK {i + 1} OF {total} — do not start the others yet:\n{item['text']}\n\n"
            "Actually PERFORM this task using your tools (write/edit files, run commands) — do "
            "not merely describe what you would do. The task is complete only once the real "
            "change exists (e.g. the file is written, the command has run)."
        )
        try:
            res = handle_task(prompt, budget=budget, emit=emit, approve=approve,
                              review=review, stream=stream, acceptance=acceptance,
                              model_override=model_override)
            item["status"], item["result"] = "done", (res or "")[:600]
        except Exception as e:
            item["status"], item["result"] = "error", f"{type(e).__name__}: {e}"[:300]
        _progress(i + 1)

    icon = {"done": "✅", "error": "⚠️", "skipped": "⏭️"}
    lines = [f"{icon.get(p['status'], '▫️')} Task {i + 1}: {p['text']}"
             for i, p in enumerate(program)]
    done = sum(1 for p in program if p["status"] == "done")
    head = f"Ran {done}/{total} tasks in sequence."
    detail = "\n\n".join(f"**Task {i + 1}: {p['text']}**\n{p['result']}"
                         for i, p in enumerate(program) if p.get("result"))
    return head + "\n\n" + "\n".join(lines) + (("\n\n---\n\n" + detail) if detail else "")
