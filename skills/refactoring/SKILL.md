---
name: refactoring
description: Restructure existing code without changing its behavior — extract, rename, simplify, decouple, remove duplication. Use when improving structure/readability of working code.
keywords: [refactor, restructure, clean up, simplify, extract, rename, decouple, deduplicate, technical debt, tidy, reorganize, modularize]
agents: [coder, fast-coder]
---

# Refactoring safely

Refactoring changes *structure*, never *behavior*. The safety net is tests.

## Process
1. **Pin behavior first.** Make sure there are passing tests that cover what you're about to
   change. If coverage is thin, add characterization tests that capture current behavior
   BEFORE refactoring — and run them green first.
2. **Understand the shape.** Use `repo_map`/`grep` to see the callers and the surrounding
   architecture. Match the existing patterns; don't impose a new style mid-file.
3. **Small, reversible steps.** One transformation at a time (extract a function, rename,
   inline, split a class), and **run the tests after each step**. Never batch ten changes
   and hope.
4. **Keep the public interface stable** unless the task says otherwise; update every caller
   in the same pass (grep for them) so nothing breaks.
5. **Delete, don't comment out.** Dead code goes; git remembers it.
6. **Verify no behavior drift** — the full suite must be green at the end, with the same
   results as before. If a test had to change, that's a behavior change: call it out.

## Anti-patterns
- Refactoring with no tests as a safety net. Mixing a refactor with a feature/bugfix in one
  messy change. "Improving" code by rewriting a whole module you didn't need to touch.
