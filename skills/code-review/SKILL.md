---
name: code-review
description: Review existing code and report only high-signal, confirmed findings — real bugs, security issues, and clear guideline violations — never style nits or speculation. Use when the task is to review, audit, or critique code or a change/PR.
keywords: [review, code review, audit, critique, assess, inspect, pr, pull request, merge, diff, feedback, findings, vulnerabilities, quality]
agents: [code-reviewer, critic]
---

# High-signal code review

A review full of noise gets ignored. Report **only findings a reasonable engineer would act on**, and verify each one before you list it.

## What to flag (high-signal only)
1. **Correctness** — code that won't compile/parse, or clear logic errors that produce a wrong result, crash, hang, or data loss.
2. **Security** — injection, unsafe deserialization, XSS, XXE, secret leaks, missing authorization, disabled TLS (see the `security-guidance` skill for the catalog).
3. **Guideline violations** — an unambiguous breach of a stated project rule (CLAUDE.md / acceptance criteria / an explicit requirement).

## What NOT to flag
- Style, formatting, or naming preferences; anything a linter/formatter would catch.
- Subjective "could be nicer" refactors that don't fix a defect.
- Pre-existing issues outside the change under review (unless they're a live security hole).
- Hypotheticals you can't tie to a concrete failing input or path — if you can't say *how* it breaks, it's not a finding.

## Method (confirm before you claim)
1. **Read the relevant files first**, and run the tests if a suite exists — real evidence beats guessing.
2. For each candidate finding, **rate your confidence 0–100** (0 = probably a false positive, 100 = certain). **Drop anything below ~80.** When unsure, re-read the code path or write/run a tiny check — don't pad the report to look thorough.
3. **Re-verify each surviving finding**: state the exact input/state that triggers it and the wrong outcome. If you can't, cut it.
4. Prefer fewer, certain findings over many maybes. "No high-signal issues found" is a valid, valuable result.

## Output
A **prioritized** list — **Critical / Major / Minor** — each item with:
- `file:line`, a one-line description of the actual defect,
- the concrete failure (input → wrong result) or the exact rule broken,
- a specific, minimal fix.

Don't rewrite the whole codebase; fix Critical/Major precisely if asked to apply changes.
