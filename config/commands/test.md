---
description: Run the test suite and fix what fails
argument-hint: "[pytest args]"
---
Run the project's tests and make them pass. Run:

!`python -m pytest $ARGUMENTS -q`

If anything fails, diagnose the root cause, apply the fix, and re-run until green.
Report what was failing and what you changed. Do not weaken or delete a test to make
it pass.
