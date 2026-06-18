# HANDOFF — read this first

_The single entry point for a new chat. **Current state + next tasks live here**; durable
rules are in `CLAUDE.md`; full backlog in `docs/BACKLOG.md`; change history in `git log`.
For "what it can do" see `docs/CAPABILITIES.md`; "how it works" `docs/PROJECT_OVERVIEW.md`._

## Current state — LIVE in production, now PUBLIC
- **Deployed 24/7** on an **Oracle Always-Free ARM VM** (Ubuntu 24.04, 2 OCPU / 12 GB, at
  `/home/ubuntu/agent_system`) as a **systemd service `agentcore`** on `0.0.0.0:8800`.
- **Public URL: `https://agentcore.tail1d9a60.ts.net`** via **Tailscale Funnel** (free, no
  domain purchased, real Let's-Encrypt-backed HTTPS terminated by Tailscale). Reachable from
  any device, no Tailscale client needed on the visitor's side. VM hostname renamed
  `instance-20260614-1205` → `agentcore` (`tailscale set --hostname=agentcore`) for the
  cleaner URL. Still also reachable tailnet-privately at `http://100.89.151.102:8800` (public
  IP `140.245.226.147` is SSH only). SSH: user `ubuntu`, key in the owner's `oracle keys` folder.
- **Safety net added BEFORE going public** (`server/ratelimit.py`, PR #4): in-process per-IP
  sliding-window cap on every `/api/*` call (`AGENT_RATE_LIMIT_PER_MIN`, default 120/min) +
  login brute-force lockout on `/api/login` (`AGENT_LOGIN_MAX_ATTEMPTS`=5 /
  `AGENT_LOGIN_LOCKOUT_SECONDS`=60). Both fail OPEN on misconfig. Wired into `server/app.py`
  (middleware) and `server/api/auth_routes.py` (login endpoint).
- **CI/CD**: every push to `main` auto-deploys via a **self-hosted GitHub Actions runner**
  on the VM (`.github/workflows/deploy.yml`: reset → pip → npm build → restart). Server
  pulls privately via an SSH deploy key (remote is `git@github.com:...`).
- **Email+password login is ACTIVE** (now the only thing standing between the public URL and
  the app — see "Security follow-ups" below); **Telegram bot** runs on the server; **nightly
  backups** via cron (`scripts/backup.py --keep 14`).
- **Run/test:** local run `.\run.ps1` → http://localhost:8800. **55/55 pytest** (`python -m
  pytest tests/ -v`). Smoke **158/158** (`scripts\smoke_test.py`). Rebuild UI after frontend
  changes: `npm --prefix web run build`.
- **Diagnostics**: `python3 scripts/inspect_run.py --list` / `<session_id>` — read-only dump
  of a run's full event timeline, span-tree (cost/tokens/duration), generated workspace files,
  and last stored message. Use this whenever asked "what did a run actually do."

## Last session (2026-06-18) — observability tool, real-run deep-dive, public exposure
1. **`scripts/inspect_run.py`** (PR #3, merged) — read-only diagnostic dump (see above). Built
   specifically so a *new chat with no filesystem access to the VM* can still verify what a
   run actually did, by having the owner paste its output.
2. **Deep-dive analysis of a real multi-turn live session** (observation only, no fixes
   applied yet — owner explicitly asked to observe before deciding what to fix). Found 7
   concrete issues, now tracked in `docs/BACKLOG.md` under "Orchestration issues found via
   live trace analysis": garbled tool-call tokens leaking into the final answer, tier-3
   research hitting the iteration cap and returning unresolved text as "final", the LEAD
   re-planning an identical template 7× before acting, tier/agent cost-tier mismatches, a
   skill over-triggering on trivial questions, cross-project workspace collisions in one chat
   session, and a `run_bash`/`write_file` path-convention mismatch causing a false
   "escapes workspace" block. **Also unresolved:** session `6dc676e500a541e9b966849004545c70`
   has zero trace events — not yet investigated.
3. **`server/ratelimit.py`** (PR #4, merged) — see "Current state" above.
4. **Went public via Tailscale Funnel** — see "Current state" above. Funnel CLI syntax has
   changed across Tailscale versions; the working flow on the current version was:
   `sudo tailscale serve reset` → `sudo tailscale funnel --bg 8800` → `tailscale funnel status`.
   (`tailscale funnel <port> on` from older docs no longer works — `funnel --help` is the
   source of truth if it changes again.)

### Security follow-ups now that the URL is public (not yet done)
- Consider rotating/strengthening `AGENT_LOGIN_PASSWORD` since the login page is now
  internet-facing (it was previously Tailscale-gated as a second layer).
- Watch for repeated 401s/429s on `/api/login` in service logs (`journalctl -u agentcore`) as
  a sign of scanning/brute-force attempts; the lockout in `ratelimit.py` mitigates but doesn't
  alert.
- Encrypting stored API keys at rest (already in `docs/BACKLOG.md`) matters more now.

## Earlier session (2026-06-16) — reliability + cost overhaul, verify sandbox, CI green

Replicated the Claude Code workflow and fixed the root causes of multi-minute hangs and the
53m/130k-token runaway run. All merged to `main` (PR #1), **CI green 158/158**.

1. **Hard wall-clock timeout on every model call** (`core/llm.py`) — litellm's own `timeout=`
   was NOT reliably honored (a NIM call ran ~139s despite `timeout=45` and returned OK, so no
   error → breaker never tripped). Now each `completion` runs on a worker bounded by us; a
   stall raises a fallbackable `Timeout`. Toggle `AGENT_HARD_TIMEOUT=0`.
2. **Circuit breaker** (`core/llm.py` `_BREAKER`) — a failed model is skipped for
   `AGENT_BREAKER_COOLDOWN`s (60) so later steps don't re-pay the timeout each time.
3. **Bounded streaming** (`core/llm.py` `_iter_stream_bounded`) — same gap closed for the
   stream path via a per-chunk queue watchdog; stall falls back to the bounded non-stream path.
4. **Smarter critic gating** (`core/orchestrator.py` `_auto_review`) — tier-2 build work skips
   the redundant critic when the Docker sandbox is live (agent self-verifies in-loop); critic
   still runs when no sandbox. Tier 3 always reviewed. `AGENT_ALWAYS_REVIEW=1` forces it on.
5. **Capped context tokens** (`core/registry.py` `context_budget`) — was ~70K/round on a 128K+
   fleet; capped at `AGENT_MAX_CONTEXT_TOKENS` (24000). Set 0 to disable.
6. **Preloaded verify image** — `docker/verify.Dockerfile` + `docker/build-verify-image.sh`
   bake python+node+pytest+common deps so the verify loop runs a suite OFFLINE with
   `--network none` (no egress). VM now runs `AGENT_BASH_DOCKER_IMAGE=agent-verify:latest`.
7. **Other fixes** — tier recalibration (single-file work → tier 2 not 3), greeting→Gemini
   fast-path (dodges NIM rate-limit), denial-spin guard, `run_bash` output clipped
   (`AGENT_BASH_OUTPUT_CAP`), `deepseek-v4-pro` demoted to fallback, coder won't spin on
   impossible installs, `scripts/flow_benchmark.py` for before/after numbers.
8. **5 latent bugs on `main` fixed** (surfaced by CI as each crash cleared): `tool_calls`
   NameError in the master loop (+ stream dict vs object normalization), stale `edit_file`
   replace_all test (read_file now wraps), `run_bash` unregistered → policy-gate crash (now
   always registered, CRITICAL+human when no Docker), missing `os` import in `approvals.py`,
   stale MASTER_SYS / deepseek-primary test assertions.

## Next tasks (immediate — full list in `docs/BACKLOG.md`)
1. **Decide which of the 7 orchestration issues to fix** *(owner decision, not yet made)* —
   full list + evidence in `docs/BACKLOG.md` "Orchestration issues found via live trace
   analysis". The owner explicitly wants to observe real runs before prioritizing fixes;
   re-run `scripts/inspect_run.py <session_id>` on more sessions if more evidence is wanted.
2. **Investigate the zero-trace session** `6dc676e500a541e9b966849004545c70` — `inspect_run.py`
   found no trace file at all for it; unclear if it never ran or traces failed to write.
3. **Validate the perf fixes** *(VM, pending — the one thing not yet confirmed)* — run
   `python3 scripts/flow_benchmark.py` and compare to the 53m/130k-token baseline (greeting
   should be ~1-2s; the REST-API build should finish under cap with no rate-limit cascade).
4. **Add 3 NVIDIA NIM keys** *(UI Settings or server `.env`: `NVIDIA_NIM_API_KEY_1..3`)* →
   ~160 RPM pooled, removes the rate-limit contention that dominated the slow runs.
5. **Activate repo mode on the server** *(SSH, ~5 min)* — add `GITHUB_TOKEN` to server `.env`;
   run `python scripts/test_repo_mode.py --repo nikethan16/agent_system` to confirm E2E.
6. **Off-site backups** *(one line, SSH)* — set `BACKUP_UPLOAD_CMD` in server `.env` so
   nightly backups leave the VM (rclone/s3/rsync to a second location).
7. **Mobile responsive pass** — Claude-style UI verified on desktop; phone drawers/panels need
   a look and CSS tweaks.
8. *(minor)* bump CI actions off deprecated Node-20 (`actions/checkout@v4`, `setup-python@v5`).

## Context for the next chat (don't re-discover)
- **`.env` (local + server, gitignored)** has working keys: `GEMINI_API_KEY`,
  `NVIDIA_NIM_API_KEY`, `SEARCH_API_KEY` (Tavily), `EMBED_MODEL=gemini/gemini-embedding-001`.
  Server `.env` also has `AGENT_AUTH_TOKEN`, `AGENT_LOGIN_EMAIL/_PASSWORD`,
  `AGENT_DAILY_USD_CAP=2.0`. ANTHROPIC/OPENAI/DEEPSEEK/OPENROUTER are placeholders.
- **Shell sandbox is now ACTIVE on the VM** (2026-06-16): `AGENT_DISABLE_BASH` removed and
  `AGENT_BASH_DOCKER_IMAGE=agent-verify:latest` (built via `docker/build-verify-image.sh`;
  python+node+pytest+common deps, runs `--network none`). The older `agent-sandbox:arm64`
  image also exists. For repo mode add `GITHUB_TOKEN`; `bridge` network only for fresh installs.
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
