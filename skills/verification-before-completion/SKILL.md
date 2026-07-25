---
name: verification-before-completion
description: Before marking any step or task done, prove it actually worked against real evidence instead of assuming. Use when finishing a task, closing out a step, or about to claim success.
keywords: [verify, verification, done, complete, finish, finished, confirm, validate, acceptance, criteria, works, success, ready, deliver, check]
agents: [coder, fast-coder, frontend, data-analyst, doc, research, repo-engineer]
---

# Verify before you call it done

"Done" means *demonstrated*, not *believed*. The most common failure mode is claiming success without checking — a fix that was never re-run, a feature that looks wired but isn't, a test-suite reported green while one test is red. Don't do that.

## The rule
For **each step** (not just the end): before you mark it complete, ask **"what would prove this served its purpose?"** — then produce that proof.

## How to verify, by kind of work
- **Code**: run it, or its tests (`run_bash` → read the REAL exit code / output). Green means you saw green, not that you expect it. If a test is red, it is not done — fix and re-run.
- **A web UI**: render it (`check_page`) and exercise the key actions; a blank screen or a dead button is not done.
- **A multi-part spec**: re-read the acceptance criteria / feature list and confirm **each item** actually works end-to-end — no stubs, "coming soon," or placeholder data standing in for real functionality.
- **A document / analysis**: re-check it answers the actual question, and that every number traces to a real computation (not a guessed figure).
- **A research answer**: confirm each load-bearing claim is backed by a source you actually read.

## When you genuinely can't verify
If a real environment limit blocks execution (no network to install a dep, a missing tool, the same command failing the same way twice), **stop retrying**. Verify by careful inspection instead, and say so plainly: *what* you couldn't run, *why*, and what inspection you did. An honest "UNVERIFIED — couldn't execute because X" is far better than a false "done."

## Anti-patterns
- Claiming a fix works without re-running the failing case.
- Reporting "all tests pass" from expectation rather than a real run.
- Marking a spec complete with features stubbed. Padding a report with confidence you didn't earn.
