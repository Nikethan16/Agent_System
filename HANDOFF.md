# HANDOFF — read this first

_The single entry point for a new chat. **Current state + next tasks live here**; durable
rules are in `CLAUDE.md`; full backlog in `docs/BACKLOG.md`; change history in `git log`.
For "what it can do" see `docs/CAPABILITIES.md`; "how it works" `docs/PROJECT_OVERVIEW.md`._

## Current state — LIVE in production
- **Deployed 24/7** on an **Oracle Always-Free ARM VM** (Ubuntu 24.04, 2 OCPU / 12 GB, at
  `/home/ubuntu/agent_system`) as a **systemd service `agentcore`** on `0.0.0.0:8800`.
- **Private access via Tailscale** at `http://100.89.151.102:8800` (app port not public;
  public IP `140.245.226.147` is SSH only). SSH: user `ubuntu`, key in the owner's
  `oracle keys` folder.
- **CI/CD**: every push to `main` auto-deploys via a **self-hosted GitHub Actions runner**
  on the VM (`.github/workflows/deploy.yml`: reset → pip → npm build → restart). Server
  pulls privately via an SSH deploy key (remote is `git@github.com:...`).
- **Email+password login is ACTIVE**; **Telegram bot** runs on the server; **nightly
  backups** via cron (`scripts/backup.py --keep 14`).
- **Run/test:** local run `.\run.ps1` → http://localhost:8800. **55/55 pytest** (`python -m
  pytest tests/ -v`). Smoke **158/158** (`scripts\smoke_test.py`). Rebuild UI after frontend
  changes: `npm --prefix web run build`.

## Last session (2026-06-15) — security hardening, trace viewer, E2E tests

1. **Trace-viewer UI** — `server/api/traces.py` (new REST endpoint), `server/trace.py` (two
   new helpers: `load_trace` + `build_tree`), `web/src/components/TracesPanel.tsx` (new),
   `RightPanel.tsx` updated with Trace tab. Span tree: agent → tool hierarchy with cost/tokens/
   duration chips, collapsible.
2. **File +/− line counts** in run summaries — `server/api/workspace.py` (`_line_counts`,
   `compute_changes`); `server/api/ws.py` (`run_complete` carries `files: [{path, status,
   added, removed}]`); `web/src/components/Chat.tsx` `ResponseFooter` renders `file.py +42 −8`.
3. **Streamed the LEAD's final answer** token-by-token — `core/llm.py` new
   `stream_complete_chain`; `core/orchestrator.py` `_master_loop(stream=)` uses it, emitting
   `agent_token` events; intermediate thoughts clear the live bubble with a `done` event.
4. **Untrusted-content boundary** — new `core/boundary.py` `wrap()` helper applied to all 9
   external input sources (git output, workspace files, bash output, file uploads, memory
   notes, RAG chunks, MCP output, vision output, document parse).
5. **Security bugs fixed in `tools/github.py`** (found by new tests): token visible in output
   when git echoed it; directory sanitizer allowed `..` traversal. Both patched.
6. **55-case pytest suite** wired into CI — `tests/test_github.py` (35 cases for all git
   tools), `tests/test_trace.py` (10), `tests/test_workspace.py` (10). `ci.yml` updated.
7. **`scripts/test_repo_mode.py`** — live E2E smoke script (clone → edit → commit → push →
   PR) for manual verification with a real `GITHUB_TOKEN`.
8. Removed dead `web/src/components/RoadmapPanel.tsx`.
9. **`docs/SERVER_ACTIVATION.md`** — owner runbook for activating Docker sandbox + repo mode
   on the server.

## Next tasks (immediate — full list in `docs/BACKLOG.md`)
1. **Activate on the server** *(SSH, ~5 min)* — add `GITHUB_TOKEN` to server `.env`; set
   `AGENT_BASH_DOCKER_IMAGE=agent-sandbox:arm64` and `AGENT_BASH_DOCKER_NETWORK=bridge`;
   unset `AGENT_DISABLE_BASH`. Then run `python scripts/test_repo_mode.py --repo
   nikethan16/agent_system` to confirm end-to-end repo mode works live.
2. **Off-site backups** *(one line, SSH)* — set `BACKUP_UPLOAD_CMD` in server `.env` so
   nightly backups leave the VM (rclone/s3/rsync to a second location).
3. **Mobile responsive pass** — Claude-style UI verified on desktop; phone drawers/panels need
   a look and CSS tweaks.
4. **API rate-limiting** — not blocking while behind Tailscale; worth adding before any wider
   exposure (`slowapi` or a simple token bucket on `/api/`).

## Context for the next chat (don't re-discover)
- **`.env` (local + server, gitignored)** has working keys: `GEMINI_API_KEY`,
  `NVIDIA_NIM_API_KEY`, `SEARCH_API_KEY` (Tavily), `EMBED_MODEL=gemini/gemini-embedding-001`.
  Server `.env` also has `AGENT_AUTH_TOKEN`, `AGENT_LOGIN_EMAIL/_PASSWORD`,
  `AGENT_DISABLE_BASH=1`, `AGENT_DAILY_USD_CAP=2.0`. ANTHROPIC/OPENAI/DEEPSEEK/OPENROUTER are placeholders.
- **Docker image `agent-sandbox:arm64`** is built and on the server (confirmed 2026-06-15);
  just needs the env var flip to activate.
- **Python venv is `.venv`** — run as `.venv\Scripts\python.exe …`.
- **GitHub:** repo is **github.com/Nikethan16/Agent_System** (private). Repo-local commit
  identity `Nikethan <nikethan160902@gmail.com>` (don't touch global git). `gh` CLI not installed.
- **Owner's git prefs:** **no** Claude co-author trailer; split work into logical, version-wise commits.
- **Deploying:** commit → push to `main` → runner auto-deploys (~2-3 min). Server `.env` is
  **not** in git; a safety classifier blocks the agent writing server secrets — env edits are
  done by the owner over SSH.
- **Invariants (`CLAUDE.md`):** no hardcoded model names (use the registry); every model call
  via `core/llm.py` under a Budget; tools sandboxed to the session workspace.

## Doc workflow (keep it minimal)
**At session end only** (owner is wrapping up / moving to a new chat): (1) commit everything
(message = changelog), (2) update this file's _Current state_ + _Last session_ (trim older to
1-2 entries) + _Next tasks_. Touch `docs/BACKLOG.md` only if priorities shifted. Nothing else
— `STATUS.md` is frozen; `CLAUDE.md` changes only on invariant/architecture changes.
