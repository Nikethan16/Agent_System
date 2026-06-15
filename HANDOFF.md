# HANDOFF — read this first

_Last updated: 2026-06-14. The single entry point for the next chat (the prior chat may be
deleted). For "what it can do" read `docs/CAPABILITIES.md`; for "how it works"
`docs/PROJECT_OVERVIEW.md`; durable rules are in `CLAUDE.md`; **remaining work is in
`docs/BACKLOG.md`**._

## TL;DR — the project is LIVE in production
- **Deployed and running 24/7** on an **Oracle Always-Free ARM VM** (Ubuntu 24.04, 2 OCPU /
  12 GB, at `/home/ubuntu/agent_system`). Runs as a **systemd service `agentcore`** on
  `0.0.0.0:8800`.
- **Reached privately via Tailscale** at `http://100.89.151.102:8800` (no public exposure of
  the app port). Public IP `140.245.226.147` is only for SSH. SSH key:
  `C:\Users\gaura\Downloads\oracle keys\ssh-key-2026-06-14.key`, user `ubuntu`.
- **CI/CD**: every `git push` to `main` auto-deploys via a **self-hosted GitHub Actions
  runner** on the VM (`.github/workflows/deploy.yml`: git reset → pip → npm build → restart).
  The server pulls privately via an **SSH deploy key** (remote is `git@github.com:...`).
- **Email + password login is ACTIVE** (creds in the server `.env`:
  `AGENT_LOGIN_EMAIL` / `AGENT_LOGIN_PASSWORD`). **Telegram bot** runs on the server.
- **Nightly backups** via cron (`scripts/backup.py --keep 14`).
- Smoke: **158/158** (`.venv\Scripts\python.exe scripts\smoke_test.py`). Local run: `.\run.ps1`
  → http://localhost:8800. Rebuild UI after frontend changes: `npm --prefix web run build`.

## What this session did (2026-06-14) — the UI became a Claude.ai clone + login + deploy
All on branch `feat/claude-ui`, **merged to `main` and deployed live**. Web build clean; smoke 158/158.
1. **Claude-style UI rebuild** (frontend only, every feature kept wired, no backend changes):
   warm "cloud" theme + **sunburst** mark; a **centered welcome screen** (time greeting +
   composer + example chips); Claude-style **composer** (big rounded card, auto-grow, circular
   send) and **messages** (plain serif assistant prose, soft user cards); **slim header**;
   **collapsible artifacts panel** (auto-opens on first file); light + dark.
   Components: `web/src/components/{Sunburst,Login,CommandPalette,Toasts}.tsx` (new) +
   reworked `App,Chat,Composer,Sidebar,RightPanel,SettingsModal,ModelRail,MemoryPanel,FleetPanel`.
2. **Email + password login** — `Login.tsx` gates the SPA; `server/api/auth_routes.py`
   (`/api/login`, `/api/auth/config` public; `/api/me` gated) + helpers in `server/auth.py`.
   Login exchanges credentials for the existing auth token. **Account menu** (avatar + email +
   Settings / theme / Log out) replaced the old model readout bottom-left.
3. **Run summary** under each response (Claude Code-style): **time · tokens · cost · tools ·
   files edited**, plus copy / regenerate / 👍👎 **always visible**. Token tracking added to
   `core/llm.py` (`Budget.tokens` + every model-call path); `run_complete` emits `tokens`+`iterations`.
4. **Settings → 5 tabs** (General · Limits & cost · Models & keys [Tiers/Keys/Health subtabs +
   Model Lab] · Memory · Advanced [security + schedules]); Roadmap tab dropped. Panels polished.
5. **⌘K command palette** (run actions / jump to chats) + a **toast** system (errors / limits).
6. **Run Options popover** restructured (sections + toggle switches + grouped limits/acceptance).

## Earlier milestones (condensed — full detail in STATUS changelog)
- **Hosting (2026-06-14):** stood up the Oracle VM, Tailscale, self-hosted-runner CI/CD,
  systemd service, deploy key, nightly backups. See `docs/SETUP_GUIDE.md` for the full walkthrough.
- **Recommended-features pass (2026-06-13):** tool-result cache + per-call metrics + Model
  Health; unattended runs (persistent approvals, Telegram `/yes`); test-first coding + acceptance
  rubric; image/PDF artifact preview.
- **Audit-fix pass (2026-06-13):** fixed 6 real bugs (429-backoff crash, parallel-delegation
  workspace contextvar, tool calls bypassing budget, missing `/file/raw`, classifier/dispatcher
  fallback chains, routing on raw request).
- **Platform optimization (2026-06-13):** multi-key pool, fallback chains, NVIDIA NIM fleet,
  resumable Project State, scheduler, Telegram, parallel sub-agents, RAG/doc-parser, vision.
- **2026-06-07:** Tavily web search, semantic memory (Gemini embeddings), first UI declutter.

## What's LEFT
**See `docs/BACKLOG.md` for the full, prioritized list.** Headlines:
- **#1 wanted feature: "work on a repo" mode** (Claude-Code-style) — point it at a GitHub
  repo → it clones + understands it → edits + opens a PR. Engine (coder + edit_file) exists;
  needs load-repo + understand-pass + git-push glue + the Docker shell sandbox. Not built yet.
- UI polish: file `+/- line counts` in the run summary; deep-polish Health/Schedules panels;
  mobile pass on the new UI; remove unused `RoadmapPanel.tsx`.
- Optional/needs a key: image generation, Langfuse cloud tracing, ANN vector index, more connectors.
- Hardening (if exposed beyond Tailscale): API rate-limiting, encrypt stored keys, off-site backups.

## Context for the next chat (don't re-discover these)
- **`.env` (local + server, gitignored)** has working keys: `GEMINI_API_KEY`,
  `NVIDIA_NIM_API_KEY`, `SEARCH_API_KEY` (Tavily), `EMBED_MODEL=gemini/gemini-embedding-001`.
  The **server** `.env` also has `AGENT_AUTH_TOKEN`, `AGENT_LOGIN_EMAIL`, `AGENT_LOGIN_PASSWORD`,
  `AGENT_DISABLE_BASH=1`, `AGENT_DAILY_USD_CAP=2.0`. ANTHROPIC/OPENAI/DEEPSEEK/OPENROUTER are placeholders.
- **Login behavior:** the SPA shows the Sign-in screen unless `AGENT_LOGIN_*` is unset (then it
  skips login). A saved token in the browser auto-signs-you-in (that's correct) — to see the
  login screen, use the account menu → Log out, or an incognito window.
- **Python venv is `.venv`** — run as `.venv\Scripts\python.exe …` (absolute path if cwd drifts).
- **GitHub:** repo is **github.com/Nikethan16/Agent_System** (private). Repo-local commit identity
  `Nikethan <nikethan160902@gmail.com>` (don't touch global git). `gh` CLI is **not** installed.
- **Owner's git prefs:** **no** Claude co-author trailer; split work into logical, version-wise commits.
- **Deploying a change:** commit → push to `main` → the runner auto-deploys (~2-3 min, watch the
  Actions tab). Server `.env` is **not** in git — env changes are done on the server over SSH.
- **A safety classifier blocks writing secrets to the production server via the agent's own
  shell** — server `.env` credential edits must be done by the owner (SSH/nano), not automated.
- **Respect `CLAUDE.md` invariants:** no hardcoded model names (use the registry); every model
  call via `core/llm.py` under a Budget; tools sandboxed to the session workspace.

## How to resume
1. `cd C:\Project\agent_system && claude` (auto-loads `CLAUDE.md`).
2. Read `docs/CAPABILITIES.md` → this file → `docs/BACKLOG.md` (what's left) → `STATUS.md` (detail).
3. After any change: `.venv\Scripts\python.exe scripts\smoke_test.py` (keep 158/158), rebuild the
   UI if the frontend changed, and add a `STATUS.md` changelog line.
