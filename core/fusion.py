"""
fusion.py — panel-of-models + judge synthesis ("Fusion").

Ask SEVERAL models the SAME question at once, hide their identities, and let a JUDGE
model synthesize ONE best answer. This is NOT decompose+critic: every panel member
answers the whole question, and the judge MERGES / OVERRIDES (it is not a grader and
not a vote-counter). Useful on hard questions where independent takes beat any single
model — a different lever from splitting a task into subtasks.

Every model call goes through core.llm (budget-capped, key-pooled). Provider-agnostic and
offline: this module only orchestrates completions, it makes no network/tool calls itself.

Collection is quorum-grace: proceed as soon as `min_panel` answers arrive plus a short
grace window for stragglers, bounded by a hard timeout — so one slow free-tier model can't
stall the whole panel. A failed/empty member simply drops out; the judge works with whoever
answered. If only one model answers there is nothing to fuse, so it is returned directly.
"""
import concurrent.futures as cf
import time

from core.llm import complete, complete_chain, BudgetExceeded

# The judge's charter. Deliberately tells it to reason, not tally — otherwise a wrong
# majority would win. Sources are anonymized ("Source N") so brand/order bias can't creep in.
JUDGE_SYS = (
    "You are the judge of a panel. Several independent sources each answered the SAME "
    "question below; their names are hidden (Source 1, Source 2, ...). Produce ONE best "
    "final answer.\n"
    "You are NOT a vote-counter — weigh the reasoning, not the head-count:\n"
    "- Where sources agree AND are correct, state it plainly.\n"
    "- Where they conflict, resolve it: pick what is correct and say why in a phrase.\n"
    "- If the consensus is WRONG, override it.\n"
    "- If every source missed something you know to be true, ADD it.\n"
    "Answer the question directly and completely. Do NOT mention the sources, the panel, "
    "or that any judging happened — just give the final answer."
)


def _ask_one(model, question, budget, temperature, timeout, max_tokens):
    """One panel completion. Returns the answer text, or None if this member failed/was
    empty (a dropped member just doesn't contribute). BudgetExceeded is re-raised so the
    hard cap halts the whole run."""
    try:
        resp, _ = complete(model, [{"role": "user", "content": question}],
                           max_tokens=max_tokens, budget=budget,
                           temperature=temperature, timeout=timeout)
        return (resp.choices[0].message.content or "").strip() or None
    except BudgetExceeded:
        raise
    except Exception:
        return None


def _collect(futures, min_panel, grace_s, hard_timeout_s):
    """Quorum-grace collection. Blocks on wall-clock deadlines (not just completions) so a
    hung straggler can't hold us past the grace window. Returns answers in completion order."""
    answers, pending = [], set(futures)
    hard_deadline = time.time() + hard_timeout_s
    grace_deadline = None
    while pending:
        now = time.time()
        waits = [hard_deadline - now]
        if grace_deadline is not None:
            waits.append(grace_deadline - now)
        done, pending = cf.wait(pending, timeout=max(0.0, min(waits)),
                                return_when=cf.FIRST_COMPLETED)
        for f in done:
            try:
                r = f.result()
            except BudgetExceeded:
                for p in pending:
                    p.cancel()
                raise
            except Exception:
                r = None
            if r:
                answers.append(r)
        now = time.time()
        if now >= hard_deadline:
            break
        if len(answers) >= min_panel and grace_deadline is None:
            grace_deadline = now + grace_s          # quorum reached — start the straggler grace
        if grace_deadline is not None and now >= grace_deadline:
            break
    for p in pending:
        p.cancel()
    return answers


def fuse(question, panel_models, judge_model=None, judge_chain=None, budget=None,
         emit=None, min_panel=2, grace_s=8.0, hard_timeout_s=90.0,
         temperature=0.4, panel_max_tokens=2048, judge_max_tokens=4096):
    """Run the panel in parallel, collect with quorum-grace, and judge-synthesize one answer.

    panel_models : the models to ask (deduped, order preserved).
    judge_chain  : preferred — a fallback chain for the judge (reliability on the one call
                   that matters); else judge_model; else the first panel model.
    Returns the synthesized answer string. Raises RuntimeError only if NOTHING answered.
    """
    panel = list(dict.fromkeys(m for m in (panel_models or []) if m))   # dedup, keep order
    if not panel:
        raise ValueError("fuse: no panel models")

    def _e(text):
        if emit:
            try:
                emit({"type": "thought", "agent": "fusion", "text": text})
            except Exception:
                pass

    _e(f"Asking {len(panel)} models the same question in parallel…")
    ex = cf.ThreadPoolExecutor(max_workers=len(panel))
    try:
        futures = {ex.submit(_ask_one, m, question, budget, temperature,
                             hard_timeout_s, panel_max_tokens): m for m in panel}
        answers = _collect(futures, min(min_panel, len(panel)), grace_s, hard_timeout_s)
    finally:
        # Don't block on stragglers — a slow member finishes (and is discarded) in the
        # background; its own per-call timeout bounds it. cancel_futures drops any unstarted.
        ex.shutdown(wait=False, cancel_futures=True)

    if not answers:
        raise RuntimeError("fusion: no panel model produced an answer")
    if len(answers) == 1:
        _e("Only one model answered — returning it directly (nothing to synthesize).")
        return answers[0]

    _e(f"{len(answers)} of {len(panel)} models answered — synthesizing one answer…")
    sources = "\n\n".join(f"--- Source {i + 1} ---\n{a}" for i, a in enumerate(answers))
    msgs = [{"role": "system", "content": JUDGE_SYS},
            {"role": "user", "content": f"QUESTION:\n{question}\n\n{sources}"}]
    if judge_chain:
        resp, _ = complete_chain(judge_chain, msgs, max_tokens=judge_max_tokens,
                                 budget=budget, temperature=0.3)
    else:
        resp, _ = complete(judge_model or panel[0], msgs, max_tokens=judge_max_tokens,
                           budget=budget, temperature=0.3)
    out = (resp.choices[0].message.content or "").strip()
    return out or answers[0]           # judge came back empty -> best-effort: a panel answer
