# OpenCode vs. AGENT // CORE — feature gap analysis (2026-07-11)

Research basis: OpenCode's open MIT repo + docs (opencode.ai/docs) mapped against our
codebase. **Bottom line:** we match or exceed OpenCode on the *agent engine, tooling,
permissions, config-driven model swap, memory, and web UI*. OpenCode's real edge is
**terminal-native delivery** (TUI/CLI/SDK), **real LSP + formatters**, a **user-authored
slash-command system**, **`@file` mentions**, **public session sharing**, and a
**git-bot** trigger. Those are our concrete gaps — and since OpenCode is open source, any
of them is ours to port; not doing so is a choice, not a limitation.

## Capability matrix (condensed)

| Feature | OpenCode | Ours | Where |
|---|---|---|---|
| Agentic loop | ✅ | **HAVE** | core/agent.py, core/orchestrator.py |
| read/write/edit/grep/glob/list | ✅ | **HAVE** | core/tools.py, core/toolbelt.py |
| bash (sandboxed) | ✅ | **HAVE** | run_bash + Docker sandbox |
| webfetch / websearch | ✅ | **HAVE** | tools/web.py (Tavily) + SSRF guard |
| subagents / task | ✅ | **HAVE (stronger)** | delegate + ~18 specialists + blackboard |
| todo list | ✅ | **HAVE** | write_todos in the lead loop |
| skills (SKILL.md) | ✅ | **HAVE (stronger)** | Skills Hub + GitHub sync + security scan |
| permissions allow/ask/deny | ✅ | **HAVE (stronger)** | allowlist→policy→AI review→human→audit |
| plan mode | ✅ | **HAVE** | handle_task(plan_only=…) |
| custom agents | ✅ | **HAVE** | config/agents.yaml (YAML) |
| config file | ✅ | **HAVE** | config/*.yaml |
| providers/models + swap | ✅ | **HAVE (stronger)** | models.yaml, cost-first routing, RoutingEditor, Model Lab |
| MCP | ✅ | **HAVE** | tools/mcp.py + config/mcp.yaml |
| rules file (AGENTS.md) | ✅ | **HAVE** | project_notes() injection |
| checkpoints / undo | ✅ | **HAVE** | per-turn snapshot + restore |
| session management | ✅ | **HAVE** | SQLite sessions/projects/jobs |
| web UI | basic | **HAVE (stronger)** | full React app |
| memory | ❌ | **HAVE** | 4-type semantic memory |
| **apply_patch (multi-file diff)** | ✅ | **HAVE** | core/tools.py apply_patch |
| **real LSP (diagnostics)** | ✅ | **HAVE** | core/lint.py (ruff, pyflakes fallback) + `diagnostics` tool + post-edit hook |
| **formatter-on-edit** | ✅ | **HAVE** | AGENT_FORMAT_ON_EDIT (black) |
| **user `/commands`** | ✅ | **HAVE** | core/commands.py, config/commands, `/` menu + palette |
| **`@file` mention in composer** | ✅ | **HAVE** | Composer.tsx @ picker |
| **session sharing (public link)** | ✅ | **MISSING** | markdown export only |
| **TUI / CLI / SDK** | ✅ | **PARTIAL** | API + run.ps1; no unified CLI |
| **git-bot (webhook trigger)** | ✅ | **PARTIAL** | repo-engineer exists; no webhook |

## Prioritized gaps to close (reach parity)

**High value — ✅ all closed**
1. ~~**`@file` mention in the composer**~~ — DONE. Picker in `web/src/components/Composer.tsx` inlines a file path.
2. ~~**User-authored `/commands`**~~ — DONE. `core/commands.py` loads `.md` templates (`$ARGUMENTS`/`$1..$9`, `!shell` via the sandbox, `@file`) from `config/commands` (+ `AGENT_COMMANDS_DIR`); expanded in `server/chat.py`; surfaced in the composer `/` menu + ⌘K palette (`GET /api/commands`).
3. ~~**Real LSP tool**~~ — DONE. `core/lint.py` runs a real analyser (ruff, pyflakes+compile fallback) as the `diagnostics` tool (granted to the 5 code agents) and in the post-edit hook. Static-only, workspace-confined.

**Medium**
4. **`apply_patch`** — multi-file unified-diff apply; reuse checkpoint diff code; register in `core/toolbelt.py`.
5. **Formatter-on-edit** — optional ext-keyed post-write hook (black/prettier/gofmt).
6. **JSON session export/import** — `server/api/sessions.py`; public share link is a bigger, security-gated task.
7. **Bash glob-allow policy maps** — OpenCode-style `{"git *":"allow"}` in `config/policy.yaml`.

**Low**
8. **Thin CLI** (`run`/`serve`/`attach`/`stats`) wrapping the API for headless automation.
9. **`question`/clarify tool** distinct from approvals.
10. **Git-bot webhook** trigger for repo-engineer.

Deliberately out of scope (OpenCode's terminal-first delivery, not our web model): TUI,
desktop app, IDE extension, keybinds. The CLI item (8) captures the useful subset.

## What WE have that OpenCode doesn't (our differentiators)
- **Multi-agent orchestration** — lead + delegate to ~18 declarative specialists on a shared blackboard.
- **Layered security** — least-privilege → policy gate → **AI security-manager** → human → audit log.
- **Cost-first model routing + Model Lab + UI routing editor + model-scout** — vs OpenCode's paid Zen gateway.
- **4-type semantic memory** (working/episodic/semantic/procedural).
- **Rich web app** — live activity, artifact preview, trace span-tree, fleet, schedules, projects, jobs, checkpoints.
- **Skills Hub** — GitHub sync with **provenance + static security scan + human-gated enable** (safer than raw skill loading).
- **Provider-agnostic invariant** structurally enforced + **daily global spend cap**.
