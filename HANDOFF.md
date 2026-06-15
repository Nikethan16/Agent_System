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
- **Run/test:** local run `.\run.ps1` → http://localhost:8800. Smoke **158/158**
  (`.venv\Scripts\python.exe scripts\smoke_test.py`). Rebuild UI after frontend changes:
  `npm --prefix web run build`.

## Last session (2026-06-15) — repo mode + Docker sandbox + tracing + ANN index
Branch `claude/serene-lamport-r1ix0k`. Code done + pushed; smoke 158/158.
1. **"Work on a repo" mode** — `tools/github.py` (git clone/status/diff/log/checkout/commit/
   push + create_pull_request via GitHub REST), a `repo-engineer` agent, a `repo` playbook.
   push/PR are `requires_human`. _Deviation to confirm:_ PR uses GitHub **REST API** (self-
   contained), not the originally-agreed MCP path.
2. **Docker sandbox hardened** — `core/tools.py`: host-shell fallback removed (fails closed);
   hardened `docker run`. `run_bash` → RISK_WRITE (no human click) when `AGENT_BASH_DOCKER_IMAGE` set.
3. **Langfuse span-tree tracing** — `server/trace.py` rewrite; core stays offline via a
   callback hook + `_span_ctx` ContextVar in `core/llm.py`.
4. **ANN vector index** — `server/vectorstore.py` (NumPy, full-corpus); `memory.recall` +
   `rag.retrieve` use it with graceful fallback.
> Also: docs flow minimized — one living HANDOFF, git log as changelog, STATUS frozen, CLAUDE de-bloated.

## Next tasks (immediate — full list in `docs/BACKLOG.md`)
1. **Activate the 2026-06-15 features on the server** (operational, not code): build an ARM64
   sandbox image + set `AGENT_BASH_DOCKER_IMAGE`, unset `AGENT_DISABLE_BASH`; add `GITHUB_TOKEN`;
   set `AGENT_BASH_DOCKER_NETWORK=bridge` for clone/installs; optional `LANGFUSE_*` + `pip install
   langfuse`. Then run an end-to-end repo-mode test.
2. **Trace-viewer UI panel** for the new span tree.
3. **UI polish**: file +/- line counts in run summaries; Health/Schedules panels; mobile pass.

## Context for the next chat (don't re-discover)
- **`.env` (local + server, gitignored)** has working keys: `GEMINI_API_KEY`,
  `NVIDIA_NIM_API_KEY`, `SEARCH_API_KEY` (Tavily), `EMBED_MODEL=gemini/gemini-embedding-001`.
  Server `.env` also has `AGENT_AUTH_TOKEN`, `AGENT_LOGIN_EMAIL/_PASSWORD`,
  `AGENT_DISABLE_BASH=1`, `AGENT_DAILY_USD_CAP=2.0`. ANTHROPIC/OPENAI/DEEPSEEK/OPENROUTER are placeholders.
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
