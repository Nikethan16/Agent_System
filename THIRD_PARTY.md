# Third-party notices

This project is our own code (Python / FastAPI / React). It has **no runtime dependency** on
any third-party agent framework — there is no external agent process, no SDK call to another
coding agent, nothing to `serve`. The notices below cover designs we **studied and
reimplemented** in our own code so we fully own and control them.

---

## OpenCode (https://github.com/sst/opencode)

**License:** MIT · **Copyright (c) 2025 opencode**

We studied OpenCode's open-source (MIT-licensed) TypeScript source to learn how a strong
agentic coding harness handles file edits, file reads, code search, and tool-argument
validation. **No OpenCode source files are copied into this repository.** Our code is an
independent Python implementation. Two levels of derivation are recorded for transparency:

### Substantially derived (algorithm ported to Python)
- **Fuzzy edit-matching cascade** — `core/tools.py` (`edit_file` and its `_replacers`).
  Our multi-strategy matcher (exact → line-trimmed → whitespace-normalized →
  indentation-flexible → block-anchor-by-similarity) is a Python reimplementation of the
  algorithm in OpenCode's `packages/opencode/src/tool/edit.ts`. We use a tighter block-anchor
  similarity threshold and a reduced strategy set (see the module docstring for the rationale),
  but the core idea — try progressively looser, **bounded** match strategies and refuse rather
  than guess — is theirs. The function carries a header comment crediting OpenCode + this notice.

### Design-inspired (independent reimplementation, not a port)
These took the *idea* from OpenCode but were written fresh against our architecture:
- **Read with offset/limit, line numbers, byte/line caps and pagination hints** — `core/tools.py`
  (`read_file`); cf. OpenCode `tool/read.ts`.
- **`grep` / `glob` code-search tools** — `core/tools.py`; cf. OpenCode `tool/grep.ts`,
  `tool/glob.ts` (theirs shells to ripgrep; ours is pure-Python and sandboxed to the workspace).
- **Tool-argument schema validation before execution** ("rewrite your call" on mismatch) —
  `core/toolbelt.py` + `core/agent.py`; cf. OpenCode `tool/tool.ts`.
- **Routing malformed/raw tool-call output to a repair path instead of surfacing it** —
  `core/agent.py` + `core/orchestrator.py`; cf. OpenCode `session/llm.ts` (`invalid` tool).

The full MIT license text for OpenCode is available at the URL above.
