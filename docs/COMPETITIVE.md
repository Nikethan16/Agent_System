# Competitive Analysis — features from peer agent tools

_Researched 2026-05. What leading agentic tools offer, what we integrated, and what
we recommend next._

## Tools surveyed
- **Claude Code** — terminal/IDE coding agent: plan mode, slash commands, subagents /
  agent teams, hooks (PreToolUse guardrails), MCP, plugins, checkpoints, skills,
  context management.
- **OpenAI Codex CLI** — sandbox modes + approval policy (`/permissions`: read-only /
  auto / full-access), permission profiles.
- **Cursor** — IDE-first; Agents Window runs multiple agents across repos.
- **Cline** — VS Code agent; **Plan & Act** modes require explicit permission before
  each file change; MCP; parallel terminal agents.
- **Aider** — terminal pair-programmer; **git-native checkpoints** (every edit a
  commit; revert/branch any session); repo map.

## Feature comparison vs. AGENT // CORE
| Capability | Claude Code | Codex | Cursor | Cline | Aider | **Us** |
|---|---|---|---|---|---|---|
| Multi-agent / subagents | ✅ | — | ✅ | 🟡 | — | ✅ supervisor + dispatcher + specialists |
| Task decomposition / plan | ✅ | 🟡 | ✅ | ✅ | — | ✅ supervisor + **plan-first mode** |
| Approval / permission modes | ✅ hooks | ✅ | 🟡 | ✅ Plan/Act | — | ✅ auto/careful/trusted + manager agent |
| Human-in-the-loop tool gate | ✅ | ✅ | 🟡 | ✅ | — | ✅ + a security-manager agent |
| Checkpoints / rewind | ✅ | 🟡 | 🟡 | 🟡 | ✅ git | ✅ workspace snapshots |
| Slash commands | ✅ | ✅ | 🟡 | 🟡 | ✅ | ✅ /new /export /model /mode /help |
| MCP / external connectors | ✅ | 🟡 | 🟡 | ✅ | — | ✅ real stdio adapter (`config/mcp.yaml`) |
| Config-driven extensibility | ✅ plugins | ✅ profiles | — | 🟡 | — | ✅ 3 registries (models/agents/tools) |
| Artifact / file preview | 🟡 | — | ✅ | ✅ | — | ✅ md/code/**HTML live preview** |
| Persistent chat history | ✅ | ✅ | ✅ | ✅ | git | ✅ SQLite |
| Budget / cost caps | 🟡 | 🟡 | 🟡 | ✅ BYOM | 🟡 | ✅ hard per-run caps |
| Audit log | 🟡 hooks | 🟡 | — | — | git | ✅ append-only |
| Token-by-token streaming | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ events stream (token todo) |

## What we integrated this round (and why)
- **Permission modes (auto / careful / trusted)** — mirrors Codex `/permissions` and
  Cline's Plan/Act. Lets you dial the friction: ask only for irreversible actions,
  ask for everything, or trust the agent (hard-blocks still apply). High value, fits
  our existing gate. → `server/approvals.py`, composer selector, `/mode`.
- **Checkpoints / rewind** — Aider's git-checkpoint idea, generalized to a workspace
  snapshot before every turn with one-click restore. Safety net for destructive edits.
  → `server/db.py`, `/api/sessions/{id}/checkpoints|restore`, Checkpoints panel.
- **Slash commands** — Claude Code-style quick actions (`/new`, `/export`, `/model`,
  `/mode`, `/help`). Low cost, big ergonomics. → `web/src/lib/store.ts`.
- **Export conversation** — download a chat as markdown (common across tools).
- **Plan-first mode** (Claude Code / Cline Plan-Act) — the supervisor decomposes,
  shows the plan, and STOPS; you approve and it executes the approved steps. → toggle
  in the composer + a "Run this plan" banner; `orchestrator.handle_task(plan_only=…)`.
- **Real MCP adapter** (Claude Code / Cline) — a working stdio JSON-RPC client reads
  `config/mcp.yaml`, launches each server, discovers its tools, and registers them as
  `mcp__<server>__<tool>` with our risk labels, granted only to the listed agents. A
  bundled example server makes it work out of the box; point it at GitHub/Slack/DB/etc.
  → `tools/mcp.py` + `tools/mcp_example_server.py`.

We **already had** the multi-agent core, config-driven extensibility, the layered
human-in-the-loop gate, budget caps, artifact preview, and persistence — so each round
focused on the gaps that gave the most leverage.

## Also integrated since
- **Critic / QA pass** (Cline-style human-in-the-loop quality) — with `review=True`,
  the `critic` agent judges each worker on concrete pass/fail and the worker gets ONE
  retry with feedback. Toggle in the composer. → `orchestrator._review`.
- **Token streaming** (all tools) — `core/llm.py:stream_complete()` streams the
  synthesized final answer as `token` events the UI types out live.
- **Cross-session memory** — `server/memory.py` recalls relevant notes from past chats
  (offline lexical scorer; embedding-ready seam) and injects them as context.
- **Diff view** (Cursor/Cline) — the artifact viewer has source / preview / **diff**;
  diff compares the current file against the pre-turn checkpoint (`/file/diff`).

## Recommended next (deliberately deferred)
1. **Per-turn token streaming** — stream tool-using agent turns too (final-answer
   streaming is done). _Medium value, medium effort (tool-call delta assembly)._
2. **Embedding-backed memory** — swap lexical recall for vector embeddings (seam ready).
3. **Parallel independent subtasks** (Cursor Agents Window / Cline parallel agents) —
   run genuinely independent subtasks concurrently (dependents stay sequential).
4. **Task queue + tracing** — unattended runs (Redis/RQ) and Langfuse/LangSmith traces.

## Where we intentionally differ
- **Supervisor + blackboard over free-form agent chatter** — predictable and
  budget-safe; we avoid uncapped peer-to-peer messaging.
- **A security *manager agent* in addition to deterministic rules + human** — most
  tools stop at rules/human; the manager-agent review is an extra contextual check
  before irreversible actions.

## Sources
- [Claude Code Features & Settings Reference 2026](https://hidekazu-konishi.com/entry/claude_code_features_settings_reference_2026.html)
- [Claude Code CLI: Hooks, MCP, Skills](https://blakecrosley.com/guides/claude-code)
- [Claude Code Agent Teams, Subagents & MCP — 2026 Playbook](https://www.developersdigest.tech/blog/claude-code-agent-teams-subagents-2026)
- [OpenAI Codex — Agent approvals & security](https://developers.openai.com/codex/agent-approvals-security)
- [OpenAI Codex — Sandbox](https://developers.openai.com/codex/concepts/sandboxing)
- [Agentic Coding Tools Compared 2026 (Requesty)](https://www.requesty.ai/blog/agentic-coding-tools-compared-2026-claude-code-cursor-codex-aider)
- [Cursor vs Cline (2026)](https://rize.io/ai-tools/vs/cursor-vs-cline)
- [AI Coding Agents 2026 guide (Codersera)](https://codersera.com/blog/ai-coding-agents-complete-guide-2026/)
