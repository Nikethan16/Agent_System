---
name: debugging
description: Systematically find and fix a bug, crash, failing test, or wrong output. Use when something is broken, throws an error/traceback, or behaves incorrectly.
keywords: [debug, bug, error, traceback, exception, failing, broken, crash, stack, reproduce, fix, regression, wrong, unexpected]
agents: [coder, fast-coder, data-analyst]
---

# Debugging methodically

Guessing wastes turns. Work from evidence, one hypothesis at a time.

## Process
1. **Reproduce it first.** Run the failing case with `run_bash` and read the REAL error /
   output. If there's no repro yet, write the smallest script or test that triggers it.
2. **Read the actual traceback** — the deepest frame in *our* code is usually the culprit,
   not the library line at the top. Note the file:line and the values involved.
3. **Localize before fixing.** Use `grep`/`repo_map` to find where the symbol is defined and
   used. Add a temporary `print`/log of the key values (or a failing assertion) to confirm
   *what* is actually happening vs. what you assumed.
4. **One hypothesis at a time.** State it ("X is None because Y never runs"), make the
   smallest change that would prove or fix it, and re-run. Don't change five things at once.
5. **Fix the cause, not the symptom.** A `try/except` that hides the error, or a special-case
   patch, is usually wrong — find why the bad value arose.
6. **Verify + guard.** Re-run the repro AND the full test suite. Add a test that fails before
   your fix and passes after, so the bug can't come back.

## Anti-patterns
- Editing code you haven't run. Claiming a fix without re-running the repro.
- Swallowing exceptions to make an error "go away". Widening a type to dodge a real bug.
