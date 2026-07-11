---
description: Review a file (or the current diff) for bugs and risks
argument-hint: "[path]"
---
Do a focused code review. Look for correctness bugs, unhandled edge cases, security
issues, and anything that would fail QA. Be specific: cite the line and give the fix.

Target: $ARGUMENTS

If a path was given above, its contents are here:
@$1

Recent changes in the workspace:
!`git diff --stat`
