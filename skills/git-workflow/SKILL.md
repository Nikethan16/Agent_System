---
name: git-workflow
description: Work with git safely on a repo — branch, stage, commit in logical units, and open a pull request. Use for repo tasks involving commits/branches/PRs.
keywords: [git, commit, branch, pull request, merge, rebase, push, checkout, stage, changelog, version control]
agents: [repo-engineer, coder]
---

# Working with git

Commits are the unit of review and the changelog. Keep them clean and safe.

## Rules
- **Branch off** the base for changes — never commit straight onto the default branch unless
  told to. Give the branch a descriptive name.
- **Logical, version-wise commits.** One coherent change per commit, not a giant dump. The
  message says WHAT changed and WHY in the subject (imperative, ~50 chars), details in the
  body if needed.
- **Review before you commit.** `git status` and `git diff` first; stage only what belongs in
  this commit (never blindly `git add -A` — check for stray/secret files first).
- **Never commit secrets** (`.env`, keys, tokens) or build junk. If you see them staged, stop.
- **Push / PR are irreversible outward actions** — do them only when the task asks, and expect
  a human approval gate. A PR description explains the change, how it was tested, and any risk.
- **Don't rewrite shared history** (force-push, hard reset on a pushed branch) unless
  explicitly instructed.

## Process
1. `git status` / `git diff` to see exactly what changed.
2. Branch if needed; stage the related files; commit with a clear message.
3. Repeat per logical change. Run the tests before pushing.
4. Push and open the PR only when asked; summarize what shipped.
