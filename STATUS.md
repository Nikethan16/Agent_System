# AGENT // CORE — Project Tracker

> **⚠️ FROZEN — historical snapshot, no longer maintained.** Current state and next tasks
> live in **`HANDOFF.md`**; change history is in **`git log`**; remaining work is in
> **`docs/BACKLOG.md`**. This file is kept only as a reference and to preserve inbound links.

The (historical) source of truth for **where we are** and **what's left**. Companion docs:
[`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) (what it does), [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) (how it works),
[`docs/PLACEHOLDERS.md`](docs/PLACEHOLDERS.md) (inputs you provide),
[`docs/COMPETITIVE.md`](docs/COMPETITIVE.md) (peer-tool research).

**Legend:** ✅ done & verified · 🟡 partial · ⬜ not started · ⛔ intentionally out of scope.
**How to update:** flip a status here when a feature lands; add a line to the Changelog.

---

## 0. At a glance
- **Engine + platform + app: complete and verified** (offline smoke test + eval harness green).
- **Everything implementable without your keys is done.** Remaining optional features
  only need inputs from you — all catalogued in [`docs/PLACEHOLDERS.md`](docs/PLACEHOLDERS.md).
- **Verify anytime (no keys):** `python scripts/smoke_test.py` and `python -m evals --dry-run`.

| Area | Status |
|---|---|
| 1. Engine (router/agent/llm/budget) | ✅ |
| 2. Platform (3 registries, dispatcher, supervisor, blackboard) | ✅ |
| 3. Security (least-priv → policy → manager → human → audit) | ✅ |
| 4. App backend (sessions, WS, persistence, queue, tracing) | ✅ |
| 5. App frontend (chat, activity, artifacts, approvals, toggles) | ✅ |
| 6. Quality/ops (evals, smoke test, audit, local traces) | ✅ |
| 7. Packaging (Docker, run scripts) | ✅ |
| 8. Optional capabilities (need your keys) | 🟡 (by design) |

---

## 1. Engine
| Item | Status | Where |
|---|---|---|
| Provider-agnostic model call + image + embeddings | ✅ | `core/llm.py` (`complete`, `generate_image`, `embed`, `stream_complete*`) |
| Thread-safe Budget + per-agent sub-budgets | ✅ | `core/llm.py` (`Budget`, `Budget.child`) |
| Config-driven model swap (tiers) | ✅ | `config/models.yaml` + `core/registry.py` |
| **Cost-first model selector** (cheapest capable + available) | ✅ | `registry.cheapest_for`; `model_strategy: cheapest` |
| **Model-scout agent** (research + add/remove models) | ✅ | `model-scout` agent + `/api/models/scout|catalog` |
| Difficulty router | ✅ | `core/router.py` |
| Sandboxed file/shell tools + per-session workspace | ✅ | `core/tools.py` |
| Generalized agent loop + approval hook + streaming | ✅ | `core/agent.py` |

## 2. Multi-agent platform
| Item | Status | Where |
|---|---|---|
| Tool registry + risk labels | ✅ | `core/toolbelt.py` |
| Agent registry (declarative specialists) | ✅ | `config/agents.yaml` + `core/agents.py` |
| Dispatcher (picks the agent) | ✅ | `core/agents.py:select_agent` |
| Supervisor (decompose → dispatch → synthesize) | ✅ | `core/orchestrator.py` |
| Shared blackboard (thread-safe) | ✅ | `core/blackboard.py` |
| Plan-first mode (preview → approve → execute) | ✅ | `handle_task(plan_only=…)` |
| Critic / QA pass + one retry | ✅ | `handle_task(review=True)` |
| Parallel independent subtasks (groups) | ✅ | `handle_task(parallel=True)` |
| Per-agent sub-budgets | ✅ | `agents.run` → `Budget.child` |

## 3. Security (layered)
| Layer | Status | Where |
|---|---|---|
| 0 least privilege (per-agent tool allowlist) | ✅ | `config/agents.yaml` |
| 1 tool risk labels (safe/write/critical) | ✅ | `core/toolbelt.py` |
| 2 deterministic policy gate | ✅ | `core/policy.py` + `config/policy.yaml` |
| 3 security-manager agent review | ✅ | `server/approvals.py` |
| 4 human approve/deny + permission modes | ✅ | WS + UI; `auto`/`careful`/`trusted` |
| audit log (every call + decision) | ✅ | `core/policy.py:audit` |
| **API/WS auth gate** (token, else loopback-only) | ✅ | `server/auth.py` |
| **SSRF guard** (web_fetch blocks private/metadata + redirects) | ✅ | `tools/web.py` |
| **Path-traversal guard** (UUID-validate ids before fs joins) | ✅ | `server/db.py:safe_id` |
| **Server budget ceilings + global daily spend cap** | ✅ | `ws.py`, `jobs.py`, `server/spend.py` |
| `run_bash` requires-human + `AGENT_DISABLE_BASH` kill-switch | ✅ | `core/toolbelt.py`, `core/tools.py` |

## 4. Application — backend
| Item | Status | Where |
|---|---|---|
| SQLite persistence (sessions/messages/events/checkpoints/memory/jobs) | ✅ | `server/db.py` |
| Per-session isolated workspace | ✅ | `server/db.py` + `core/tools.py` |
| Conversation manager (multi-turn context) | ✅ | `server/chat.py` |
| WebSocket live-run (stream + approvals + stop) | ✅ | `server/api/ws.py` |
| REST (sessions/messages/workspace/models/agents) | ✅ | `server/api/*` |
| Checkpoints (snapshot/rewind) + diff (`/file/diff`, `/changes`) | ✅ | `server/db.py`, `server/api/workspace.py` |
| Persistent task queue + worker | ✅ | `server/jobs.py` + `/api/enqueue` |
| **Memory — 4 types** (working summary, episodic recall, semantic facts, procedural rules) | ✅ | `server/memory.py`, `server/chat.py`, `server/api/memory.py` |
| **Model Lab** (benchmark a model across aspects, raw + pipeline, compare) | ✅ | `server/benchmark.py`, `scripts/run_benchmark.py`, `evals/benchmark.yaml`, `server/api/benchmark.py` |
| **Backups** (one-command zip of all stateful data) | ✅ | `scripts/backup.py` |
| Surgical edit tool (`edit_file`, precise snippet replace) | ✅ | `core/tools.py`, `core/toolbelt.py` |
| Tracing (per-run JSONL) | ✅ | `server/trace.py` → `data/traces/` |

## 5. Application — frontend (`web/`)
| Item | Status |
|---|---|
| Chat thread (markdown) + live agent-activity feed | ✅ |
| Session sidebar (create/switch/rename/delete) | ✅ |
| Model routing rail (live swap) | ✅ |
| Approval cards + Stop | ✅ |
| Artifacts panel: source / preview (HTML+md+**sandboxed SVG**) / **diff** / **history** | ✅ |
| Skills panel (available + applied) | ✅ |
| **Memory panel** (view/add/forget facts; approve/reject/delete rules) | ✅ |
| **Model Lab modal** ("Bench" — run + compare model scorecards) | ✅ |
| Settings: theme (persisted), approval mode, budgets, **access token**, **spent today** | ✅ |
| Per-file version history (timeline from checkpoints) | ✅ |
| Responsive layout (mobile drawers for both side panels) | ✅ |
| Checkpoints (rewind) panel | ✅ |
| Composer toggles: PLAN-FIRST · QA REVIEW · PARALLEL · STREAM · approval mode | ✅ |
| Slash commands (/new /export /model /mode /help) + export | ✅ |
| Final-answer + per-turn (opt-in) streaming | ✅ |

## 6. Quality / ops
| Item | Status | Where |
|---|---|---|
| Eval harness (one command) | ✅ | `evals/` (`python -m evals`) |
| Offline regression smoke test | ✅ | `scripts/smoke_test.py` (**60 checks**, fake model) |
| Append-only audit log | ✅ | `audit.log` |
| Local traces | ✅ | `data/traces/<session>.jsonl` |

## 7. Packaging / deploy
| Item | Status | Where |
|---|---|---|
| Dockerfile (build web + serve) + compose | ✅ | `Dockerfile`, `docker-compose.yml`, `.dockerignore` |
| Run scripts | ✅ | `run.ps1` (Windows), `run.sh` |

## 8. Optional capabilities (work with fallbacks; full power needs your keys)
| Item | Status | Needs (see PLACEHOLDERS.md) |
|---|---|---|
| `web_fetch` (research) | ✅ | nothing (keyless) |
| `web_search` (research) | ✅ | working — Tavily (`SEARCH_API_KEY` set 2026-06-07) |
| `generate_image` (image agent) | 🟡 | `image_model:` + provider key |
| Embedding-backed memory | 🟡 | `EMBED_MODEL` + key (else lexical) |
| MCP connectors | ✅ | bundled example works; real servers via `config/mcp.yaml` |
| Langfuse cloud tracing | 🟡 | `LANGFUSE_*` keys (`pip install langfuse`); **forwarder code done** (v2+v3 SDK, flush on shutdown) — local traces work now |

---

## What's left

**A. In our hands — nothing blocking.** The remaining ideas are polish, not gaps:
- ⬜ Make per-turn streaming the default with a dedicated UI lane (today: opt-in + minimal live line).
- ⬜ Fine-grained dependency **DAG** (today: parallel *groups* already cover ordered dependencies).
- ⬜ Optional Redis/RQ queue swap *code* (today: SQLite queue runs unattended; Redis is a scale upgrade).

**B. Needs your input — leave per request.** All in [`docs/PLACEHOLDERS.md`](docs/PLACEHOLDERS.md):
provider keys (🔴 for real runs), search/image/embedding keys, Langfuse keys, Redis URL, real MCP servers.

**C. ⛔ Intentionally out of scope** (matches the agreed "local single-user" decision):
multi-user **accounts / per-user data isolation** and a Postgres swap. (A single shared
**access token** + loopback-only default now exists for safe network exposure — see
`server/auth.py` — but true multi-tenant accounts are deliberately not built.)

**D. Known remaining work for a public DEPLOYMENT only** (not needed for personal/local use):
a **real shell sandbox** (container-per-run) before enabling `run_bash` on a networked host —
mitigated today by `requires_human` + `AGENT_DISABLE_BASH=1` (Docker default); broader unit tests beyond the 60-check smoke suite.

---

## Changelog
- **2026-06-15 (repo mode + Docker sandbox + tracing + ANN index)** — **Shipped four backlog items** on branch `claude/serene-lamport-r1ix0k` (commit `513eb24`, pushed). Smoke **158/158**. Code complete; live activation needs server `.env` steps (see `docs/BACKLOG.md`).
  - **"Work on a repo" mode** — new `tools/github.py` (git clone/status/diff/log/checkout_branch/commit/push + `create_pull_request` via GitHub REST; `GITHUB_TOKEN` injected into URLs, never logged), a `repo-engineer` agent (`config/agents.yaml`), and a `repo` playbook (clone→plan→branch→implement→verify→push→pr). `git push` + PR creation are `requires_human` (`config/policy.yaml`); repo content treated as untrusted DATA.
  - **Docker shell sandbox (hardened)** — `core/tools.py:run_bash` drops the unsafe host-shell fallback (fails closed unless `AGENT_BASH_DOCKER_IMAGE` is set) and hardens the container (`--cap-drop ALL`, `--security-opt no-new-privileges`, `--read-only` + tmpfs, pids/mem/cpu limits, cidfile kill on timeout). `core/toolbelt.py`: sandboxed `run_bash` is RISK_WRITE (no human click); unsandboxed stays RISK_CRITICAL + requires_human. New `AGENT_BASH_DOCKER_TIMEOUT/_MEMORY/_CPUS/_NETWORK/_PIDS`.
  - **Langfuse span-tree tracing** — `server/trace.py` rewritten into a per-run span tree (run → subagent → LLM generation with model / prompt+completion tokens / cost / latency). `core/` stays offline via `register_llm_observer` + the `_span_ctx` ContextVar (re-bound in `orchestrator._run_delegation`); `server/app.py` registers the observer at startup. New `LANGFUSE_HOST`.
  - **NumPy ANN vector index** — `server/vectorstore.py` (lazy unit-normalized matrix, vectorized cosine, full-corpus search, no `_MAX_SCAN` ceiling, invalidated on every write). `memory.recall` + `rag.retrieve` use it first, then fall back to the Python loop / lexical. New `MEMORY_VECTOR_BACKEND` (auto|numpy|none).
- **2026-06-14 (Claude-style UI + login + LIVE deploy)** — **Rebuilt the web UI as a faithful Claude.ai clone, added an email+password login, and deployed the whole app to production.** Branch `feat/claude-ui` merged to `main`; web build clean; smoke **158/158**; verified live (login flow, run summary, settings) via the dev server + a real run.
  - **Claude-style UI** (frontend only, all features kept wired): warm "cloud" theme + sunburst mark (`web/tailwind.config.js`, `Sunburst.tsx`); centered **welcome screen** (time greeting + composer + chips); Claude-style composer (rounded card, auto-grow, circular send) + messages (serif assistant prose, soft user cards); slim header; **collapsible artifacts panel** (auto-opens on first file); light + dark. Reworked `App/Chat/Composer/Sidebar/RightPanel`.
  - **Email + password login** (`server/api/auth_routes.py` — `/api/login` + `/api/auth/config` public, `/api/me` gated; helpers in `server/auth.py`; `web/.../Login.tsx`). Gates the SPA when `AGENT_LOGIN_EMAIL`+`AGENT_LOGIN_PASSWORD` are set; exchanges creds for the existing auth token. **Account menu** (avatar+email+Settings/theme/Log out) replaced the sidebar model readout.
  - **Run summary + token tracking** — `Budget.tokens` added in `core/llm.py` (every model-call path); `run_complete` emits `tokens`+`iterations`. Each response shows **time · tokens · cost · tools · files edited** with always-visible copy/regenerate/feedback (`Chat.tsx` ResponseFooter).
  - **Settings 9→5 tabs** (General · Limits & cost · Models & keys [Tiers/Keys/Health subtabs] · Memory · Advanced); Roadmap tab dropped; ModelRail/MemoryPanel/FleetPanel polished. **⌘K command palette** (`CommandPalette.tsx`) + **toasts** (`Toasts.tsx`, store slice). Run Options popover restructured.
  - **Production deploy** — Oracle Always-Free ARM VM (Ubuntu 24.04), systemd `agentcore` on :8800, Tailscale-only web access, **self-hosted-runner CI/CD** (`.github/workflows/deploy.yml`, push-to-main → pull/build/restart) via an SSH deploy key, nightly backup cron, Telegram bot live. Walkthrough in `docs/SETUP_GUIDE.md`; UI plan in `docs/UI_REDESIGN_PLAN.md`; remaining work in `docs/BACKLOG.md`.
- **2026-06-13 (recommended features)** — **Built the 4 high-impact bundles surfaced by the audit triage** (Health+caching, unattended runs, coding quality, artifacts+traces); skipped the rest (workspace branches, plan-graph DAG, connectors, browser-use). Offline smoke **147→158**; web build typechecks clean; live-server UI verified (no console errors). Per-commit detail in `git log`.
  - **Tool-result cache + per-call metrics + Model Health** (`core/cache.py`, `core/metrics.py`, `/api/fleet/health`, Settings → **Model health** panel) — web fetches / doc parses (mtime-keyed) / embeddings are cached (an all-cached embed spends nothing; only uncached texts hit the provider), and a per-model rollup (calls / errors / avg latency / fallbacks / cost) + per-key pool usage + cache hit-rates surface in the UI. Squeezes the rate-limited NVIDIA fleet and gives the call-level trace the event feed lacked.
  - **Unattended runs: persistent approvals + reattach** (`server/runs.py` RunState+Approval tables, `server/approvals.py` global resolver, `/api/sessions/{id}/active-run` + `/approvals` + `/api/approvals/{id}/resolve`) — an approval request survives a browser disconnect and is answerable from any client (UI reconnect, a second tab, or **Telegram `/yes <id>` / `/no <id>`**); the UI re-surfaces a waiting approval on session open. Telegram tasks now run in their own thread with an approval broker.
  - **Coding quality: test-first + acceptance rubric** (`config/playbooks.yaml`, orchestrator/chat/ws threading) — the coding playbook now writes tests FIRST (red→green→validate), and a user-supplied **acceptance criteria** field (Composer → Run options) is injected for the agents and given to the critic as the explicit PASS/FAIL rubric.
  - **Artifacts + traces** (FilesPanel) — inline **image + PDF preview** and binary **download** via the new `/file/raw`; per-step call trace lives in the Model Health panel.
  - **Skipped (validated, low ROI / not needed):** streaming-resilience (already degrades safely), per-session run lock (single-user edge case), RAG batch-embedding (only matters with an embed model), workspace branches (checkpoints cover it), plan-graph DAG, connectors, browser/computer use.
- **2026-06-13 (audit-fix pass)** — **Validated an external code review (Codex) and fixed the 6 findings that were real + high-impact.** Offline smoke **130→139** (a regression check per fix); web build unaffected. Per-commit detail in `git log`.
  - **#1 — 429 backoff crash (critical):** `core/llm.py` called `time.sleep()` on the rate-limit path but never imported `time`, so every first 429 raised `NameError` instead of rotating keys. Added `import time`.
  - **#5 — parallel delegations wrote to the wrong workspace (silent):** `delegate_parallel` runs each step in a `ThreadPoolExecutor` worker, and worker threads don't inherit the `using_workspace` **contextvar** — so parallel sub-agents read/wrote the global `./workspace` instead of the session workspace. The LEAD captures the run's workspace and each delegation re-binds it (`core/orchestrator.py`).
  - **#4 — tool-internal model calls bypassed the budget:** `see_image`/`safety_check`/`generate_image` used throwaway `Budget`s (and image gen had **none**), so their cost never hit the run budget or daily cap. Added a `current_budget()` contextvar bound per run (`core/llm.py`); the three tools now charge a child of it (`tools/vision.py`, `tools/safety.py`, `tools/image.py`).
  - **#10 — `/file/raw` route was missing:** the frontend (`web/src/lib/api.ts`) and the text-file endpoint both pointed at `/file/raw` for binary artifacts (e.g. generated images), but no such route existed. Added it (`server/api/workspace.py`, same sandbox guard).
  - **#3 — classifier/dispatcher skipped the fallback chains:** both used a single `model_for_tier()` call, so a down primary degraded instead of switching model. Routed both through `complete_chain(model_chain(..., "classify"))` (`core/router.py`, `core/agents.py`).
  - **#7 — routing on the full assembled context:** the classifier saw the whole history+memory+project blob (wasteful, distorts the tier). Now routes on the **raw user request** (`core/orchestrator.py`).
  - **Validated-but-deferred (not blindly implemented):** streaming-resilience (#2 — already falls back to robust non-streaming, so low ROI), per-session run lock (#6 — real but a multi-tab edge case on a single-user local tool), RAG batch-embeddings (#8 — quick win but only matters once `EMBED_MODEL` is set). The 20 forward-looking feature ideas were triaged, not auto-built.
- **2026-06-13 (session 2 cont.)** — **Robustness, doc-intelligence, safety, ops, multimodal, more UI.** Same branch; offline smoke **107→123**; web build clean; `evals --dry-run` exits 0 (CI-safe). Per-commit detail in `git log`.
  - **Task playbooks** — `config/playbooks.yaml` + `core/playbooks.py`: each task type follows a proven path (understand→plan→build one-at-a-time→validate→review) with a preferred specialist + gate per phase; the LEAD is **seeded** from it, tier-2 agents get a compact checklist, and any **uncovered** task type uses the `default` backup path. Config-driven.
  - **Agent robustness** — auto-**retry** of a failed/empty step (single-agent + delegation; `retry` event), **tool-call JSON repair**, **stuck-loop guard** (repeated identical call → forced final). `policy.audit` makes its dir + **rotates** at `AUDIT_LOG_MAX_BYTES`.
  - **Memory + pace** — recall prefers same-**project** notes (`scope_hint`), episodic **pruning** (`MEMORY_MAX_TURNS`), **classifier-cache** on the user's request, fact-extraction skipped on trivial turns.
  - **Document intelligence** — **`parse_document`** tool (markitdown→md) for FRS/specs; **RAG** over project knowledge (`server/rag.py`: chunk+embed+retrieve only relevant excerpts, lexical fallback).
  - **Content safety** — `safety_check` tool (`tools/safety.py`; model-based when `SAFETY_MODEL` set, else heuristic). **Eval coverage** for architect + data roles.
  - **Ops** — opt-in **Docker-sandboxed `run_bash`** (`AGENT_BASH_DOCKER_IMAGE`), **proactive Telegram digests** (a scheduled task in a Telegram chat pushes its result to the phone), **off-site backup hook** (`BACKUP_UPLOAD_CMD`).
  - **Multimodal** — **`see_image`** vision tool (workspace image → description via `VISION_MODEL`/routing 'vision'→llama-4-maverick); attached images point the agent to it.
  - **More UI** — at-a-glance **agent-status chips**, **Models-admin** (add/remove catalog models + when-to-use from Settings → Fleet), **Roadmap** panel (Project State Done/Next).
  - **Deferred (with rationale)**: prompt-caching G2 (low ROI on NIM — it doesn't expose it; B1 classifier-cache covers repeats), a true ANN vector index (project-first recall + pruning suffice for now), Telegram inline-button approvals (needs the bot token to build/verify), API-level rate-limiting + key-encryption-at-rest (hosting hardening), per-project budget cap + artifact-export-zip UI + LEAD final-answer streaming (polish).
- **2026-06-13** — **Platform optimization: resilience, NVIDIA fleet, memory continuity, scheduler, Telegram, parallel agents, mgmt UI, CI.** Branch `feat/platform-optimization`; offline smoke **60→107**; web build clean; key endpoints verified live on NVIDIA. Per-commit detail in `git log`.
  - **NVIDIA NIM fleet (Phase 1+4)** — integrated DeepSeek V4 Pro (LEAD), GLM-5.1 (coder), Qwen 3.5 (research), Nemotron Super/Ultra/Nano, Llama-4 Maverick, DeepSeek V4 Flash, MiniMax M3, Mistral Large 3 — all **verified live** (ids + tool-calling). Dead names dropped (kimi-k2.6 garbled tool-calls; codestral 404s). 4 new roles: **architect, data-analyst, code-reviewer, fast-coder**. Routing chains per task_type in `config/models.yaml`.
  - **Resilience engine (Phase 2, `core/keypool.py` + `core/llm.py`)** — **multi-key pool** (least-loaded, per-key ~40 rpm accounting, cooldown; `NAME_1..N` → 4 keys ≈ 160 rpm), **per-call timeout** (`AGENT_LLM_TIMEOUT`, kills cold-start hangs; `litellm.num_retries=0`), **fallback chains** (`complete_chain`, NVIDIA-first, emits `fallback`; budget = hard stop; **stale/dead model name now self-heals** instead of crashing).
  - **Memory continuity (Phase 3)** — **structured Project State** (`{goal, plan, next, artifacts}` re-injected each turn → resume "finish phase 2 → do phase 3", incl. a new chat in the same project), **project-shared workspaces**, **adaptive token-budgeted context** (killed the hardcoded 12-message window; `registry.context_budget()`/`context_window`).
  - **Scheduler** (`server/scheduler.py`, `/api/schedules`) — once/interval/daily/weekly tasks on the job queue; survives restarts; no cron daemon.
  - **Telegram control** (`server/telegram.py`) — mobile access via a long-polling bot; fail-closed allowlist; no-op until `TELEGRAM_BOT_TOKEN` set.
  - **Parallel sub-agents** — `delegate_parallel` runs independent steps concurrently (the pool makes it genuinely faster). Sharper, self-contained delegation prompts.
  - **Management UI (Phase 5)** — Settings → **Fleet & keys** (add/remove/test pooled keys, masked, live rpm; view/edit fallback chains) + **Schedules**; `fallback` activity card.
  - **CI** (`.github/workflows/ci.yml`) — smoke + offline evals + web build on every push. **New env vars** in `.env.example` (key pool, timeout, scheduler, Telegram).
- **2026-06-07** — **Web search live + dep/model fixes + semantic memory + UI redesign. Project paused.**
  Full per-item detail in `HANDOFF.md`; capabilities catalogued in `docs/CAPABILITIES.md`.
  - **Web search now works** — `tools/web.py:web_search` was a broken stub; rewrote it for
    **Tavily** (correct request + result formatting, SSRF guard + untrusted-data wrapper kept).
    Free `SEARCH_API_KEY` set in `.env`. Verified raw + through the research agent.
  - **Added missing `tenacity` dep** — LiteLLM's retry/backoff imports it; it was uninstalled,
    so every rate-limit retry crashed. Added to `requirements.txt` + installed (free-tier resilience).
  - **Fixed dead tier-3 model** — `nvidia_nim/deepseek-ai/deepseek-r1` 404s now; swapped to
    `nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5` (free, reasoning, tool-calling). `config/models.yaml`.
  - **Enabled semantic memory** — `EMBED_MODEL=gemini/gemini-embedding-001` (the docs' `text-embedding-004`
    was retired/404). Verified meaningful embeddings.
  - **Smoke test made hermetic** — wiped its own data dir each run (was leaking approved rules → 59/60 on re-run).
  - **UI redesign integrated** (Stitch design, `docs/UI_STRUCTURE_PLAN.md`): minimal composer + **Run-options
    popover**, slim top bar, right panel 6→4 tabs with badges, **5-tab Settings** absorbing Models + Memory.
    Layout/disclosure only — no backend changes, all wiring preserved. Build clean.
  - **Repo cleanup** — removed redundant/superseded docs (DOCUMENTATION, CLAUDE_PARITY, FRONTEND_BRIEF,
    UI_REDESIGN_BRIEF, architecture.html) and the legacy `ui/` panel; added `docs/CAPABILITIES.md`.
- **2026-06-06 (session 2)** — **Live validation + 4 fixes + handoff.** See `HANDOFF.md`.
  - Real-model pipeline validated end-to-end (built+ran a CLI todo app, tests pass; tier-3
    LEAD planning + delegation confirmed).
  - **Fix:** chit-chat fast-path stops greetings spinning to the iteration cap (`core/orchestrator.py`).
  - **Fix:** LEAD master loop guards empty provider `choices` (no more `IndexError` crash).
  - **Fix:** `core/router.py` retries on transient/rate-limit, re-raises budget stops, falls
    back DOWN to tier-1 instead of escalating.
  - **Fix:** `core/skills.py` intent-gates doc skills (no docx on "README"; deck→pptx intact).
  - **Langfuse** forwarder finished (v2+v3 SDK, flush on shutdown) in `server/trace.py`.
  - New docs: `HANDOFF.md`, `docs/MODEL_REQUIREMENTS.md`, `docs/UI_REDESIGN_BRIEF.md`,
    `docs/GO_LIVE.md`, `scripts/live_smoke.py`. Smoke still **60/60**.
- **2026-06-06** — **First live verification + Langfuse finish + live harness.**
  - **Ran against a real model for the first time** (Gemini key added). `live_smoke` 2/2;
    `python -m evals` 2/3 — the single fail was the Gemini **free-tier 5 req/min** rate limit
    tripping the LLM-judge call, not a code fault. The tier2 coding case wrote *and ran* a file
    (`exit=0`), confirming the surgical-edit coding harness works end-to-end on a live model.
  - **Langfuse forwarder finished** (`server/trace.py`): now resilient across SDK majors
    (v2 `trace()/event()` and v3 OTEL `create_event()/start_span()`), latches off if the SDK/keys
    are absent, and **flushes on interpreter exit + FastAPI shutdown** (`app.py` shutdown hook) so
    short-lived processes don't drop spans. Still a safe no-op without `LANGFUSE_*` keys.
  - **`scripts/live_smoke.py`** — a small, rate-limit-paced real-model health check (chat + router),
    complementing the 60-check offline smoke test. **`docs/GO_LIVE.md`** — the escalating
    verify path (offline → live health → live pipeline → app) and the free-tier rate-limit guidance.
  - **Verification:** offline smoke still **60/60**; live_smoke 2/2.
- **2026-06-03** — **Security hardening + Memory (4 types) + Model Lab + harness upgrade.**
  A large multi-part session. Full per-issue detail in `docs/REVIEW_FIXES.md` and
  `docs/MEMORY_DESIGN.md`.
  - **Security review fixes** (from a full code review): removed a leaked key + added
    `.gitignore`; **auth gate** (`server/auth.py`: `AGENT_AUTH_TOKEN` required, else
    loopback-only) wired onto every REST router + the WebSocket; **SSRF guard** in
    `tools/web.py` (blocks private/loopback/metadata IPs + re-validates redirects);
    **path-traversal guard** (`db.safe_id` UUID-validates session/checkpoint/project ids
    before any filesystem join; global `InvalidId→400`); **server budget ceilings**
    (`AGENT_MAX_USD_CEILING`/`AGENT_MAX_ITER_CEILING`) clamp client-supplied caps on WS +
    queue; `run_bash` is now `requires_human=True` with an `AGENT_DISABLE_BASH` kill-switch
    (Docker sets it on); MCP tools default fail-safe to critical+human; catalog writes are
    validated/coerced; job queue re-queues stale `running` jobs on restart; trace cache
    bounded; input validation + 404 consistency on the API. Frontend: unsanitized SVG now
    renders in a **script-disabled sandboxed iframe**; WebSocket closes on session switch +
    handles drops; central fetch wrapper with error surfacing; stable message keys; theme in
    the store (persisted); a11y on modals/rows; TS **strict** on; vendor code-splitting;
    Dockerfile copies `skills/` + runs non-root; dependency upper bounds.
  - **Global daily spend cap** (`server/spend.py`, `AGENT_DAILY_USD_CAP`, `/api/spend`,
    shown in Settings) — a cumulative ceiling above the per-run Budget.
  - **Backups** — `scripts/backup.py` zips all stateful data (DB + workspaces + checkpoints).
  - **Memory system (4 types)** — Phase A **working memory** (12-msg window + a rolling
    per-session summary of older turns), Phase B **semantic facts** (auto-extracted durable
    facts injected into every chat, deduped by key, with a **Memory panel** to view/add/forget),
    Phase C **embedding-based episodic recall** (switches on when `EMBED_MODEL` is set; lexical
    fallback otherwise), Phase D **procedural rules** (agent proposes reusable rules → you
    **approve in the UI** → only then injected as operating instructions). All extra calls are
    cheapest-tier, gated, budget-capped, best-effort. New `server/api/memory.py`.
  - **Harness upgrade (Path B — Claude-Code-style coding without the dependency)** — a
    **surgical `edit_file`** tool (exact-snippet replace + diff back to the model) so agents
    stop overwriting whole files; coder/frontend/lead prompts rewritten to explore→read→edit→
    verify; per-agent tool-round cap raised 8→14 (`AGENT_MAX_TOOL_ROUNDS`).
  - **Model Lab** — benchmark any model on a 10-task battery across **coding / reasoning /
    writing / instruction** aspects, in **raw** (model only) and **pipeline** (model+orchestration)
    modes, graded on **concrete pass/fail** (never 1-10). Runs in an **isolated subprocess**
    (own workspace + forced model, no interference with live app). UI: a **"Bench"** modal with a
    compare table. `evals/benchmark.yaml`, `scripts/run_benchmark.py`, `server/benchmark.py`,
    `server/api/benchmark.py`.
  - **Verification:** smoke suite grew 26→**60 checks** (all green); frontend `tsc --strict`
    + `vite build` clean; live API checks for auth/memory/spend/benchmark all pass.
  - **New env vars** (all optional for local use; see `docs/PLACEHOLDERS.md`): `AGENT_AUTH_TOKEN`,
    `AGENT_DAILY_USD_CAP`, `AGENT_DISABLE_BASH`, `AGENT_MAX_USD_CEILING`, `AGENT_MAX_ITER_CEILING`,
    `AGENT_MAX_TOOL_ROUNDS`, `MEMORY_MAX_SCAN`, `MEMORY_SEMANTIC_THRESHOLD`, `MAX_CHECKPOINTS`.
- **2026-06-02** — **Document skills refreshed + staging fix.** Re-imported the latest
  Anthropic `pdf`/`docx`/`xlsx`/`pptx` skills from github.com/anthropics/skills, and
  hardened `core/skills.py:stage()` to also copy each skill's **loose top-level reference
  files** (e.g. `pdf/REFERENCE.md`, `pdf/FORMS.md`, `pptx/EDITING.md`, `pptx/PPTXGENJS.md`)
  into the session workspace — previously only the `scripts/references/assets` subdirs were
  staged, so the reference docs a SKILL.md points to never reached the agent. Re-verified
  end-to-end: all doc-skill libs present in the venv, the toolchain produces real
  .docx/.xlsx/.pptx/.pdf files, selection routes correctly, smoke 26/26, live `/api/skills`
  serves all 7 skills. (The original import landed 2026-05-31 below.)
- **2026-05-31** — **Skills + quality batch "A"** (six items): (1) **Real document skills** —
  imported Anthropic's `pdf`/`docx`/`xlsx`/`pptx` skills and added the pure-Python libs
  (openpyxl, python-pptx, python-docx, reportlab, pdfplumber, pandas, Pillow, markitdown)
  to `requirements.txt`, so the team can produce real spreadsheets/decks/PDFs out of the
  box (verified live: the xlsx skill is applied + a file is produced; advanced format paths
  need optional LibreOffice/pandoc/Node — see PLACEHOLDERS row 9). Skill staging is now
  idempotent (copied once per session) and hidden from the Files panel. (2) **Smarter skill
  selection** — stopword-filtered scoring + distinctive trigger words ("deck"→pptx,
  "spreadsheet"→xlsx) and the lead can **explicitly** pull a skill via `delegate(skill=…)`.
  (3) **Skills panel** in the UI (right-panel tab) showing every skill + which were applied.
  (4) **Streaming on by default** with a dedicated live "streaming" lane in chat. (5)
  **Auto-QA**: the critic now runs automatically on substantive tasks (tri-state `review`:
  auto/force-on/off) instead of an opt-in toggle. (6) **Responsive layout** (mobile drawers
  for both side panels) + **per-file version history** (`/file/versions` + `/file/at`, a
  "history" tab on each artifact). Also fixed a latent `os` import crash in `chat.py` on
  attachments. Smoke now 26 checks (auto-review decision + skill selection/forcing).
- **2026-05-29** — **Agent Skills** (Claude-format): `core/skills.py` loads `skills/<name>/SKILL.md` (frontmatter + body), and each agent run **selects relevant skills** (progressive disclosure), **stages their bundled scripts** into the workspace, and **injects their guidance** — lifting output quality. Bundled `web-frontend`, `research-report`, `python-project`; pull more from github.com/anthropics/skills via `scripts/import_skill.py`. `GET /api/skills`; `skill` event in the activity timeline. Smoke now asserts skill selection + injection (16 checks).
- **2026-05-29** — **Core rearchitected to a Claude-Code-style master loop.** Replaced the rigid decompose→run-fixed-subtasks→synthesize flow with a single LEAD loop: seeds an explicit **todo list**, then iteratively works/updates it, **delegating** scoped steps to specialist subagents (`delegate` meta-tool, depth-limited). Model choice is now **task-aware + cost-first** (`model_for_tier(tier, task_type)`). Verified live: a complex coding task seeds a plan, delegates to the coder (which wrote + ran files), and finishes. Smoke updated to assert the master loop (todos + delegation).
- **2026-05-29** — **Claude-parity Batches 2–4** (`docs/CLAUDE_PARITY.md`): file **attachments** (upload + context, PDF text), **edit message → branch**, **"try fixing"** on errors; **Projects** (shared instructions + knowledge files injected as context) + sidebar project selector + settings modal; **Mermaid/SVG** live rendering in chat + canvas; **settings modal**, **⌘/Ctrl+K** new chat, **star/favorite** chats, **👍/👎 feedback**. Deferred: full mobile, per-file version timeline, React live-run.
- **2026-05-29** — **Claude-parity Batch 1** (`docs/CLAUDE_PARITY.md`): syntax-highlighted + copyable code blocks, message copy/regenerate, empty-state suggestion chips, artifact copy/download/**expand-to-canvas**, sidebar chat search. Roadmap for Batches 2–4 (attachments, message-edit, Projects, richer artifacts) documented.
- **2026-05-29** — **Fixes from live use:** (1) the LLM dispatcher had a `str.format()` bug (literal `{"agent"}` in the prompt) that made it silently fall back to keyword matching every time — so "explain the code" routed to the *coder* (tools) instead of an explainer. Fixed; explanations/follow-ups now go to the tool-less `general` agent. (2) Added LiteLLM `num_retries=3` + graceful agent-loop error handling so free-tier 429 rate-limits retry/degrade instead of crashing a turn. (3) Raised default iteration budget (8→24, UI 12→20) now that dispatch consumes calls. (4) UI: agent-activity timeline is collapsed by default and only shown when the team did real work (tools/plan/QA/multi-agent) — simple chats stay clean.
- **2026-05-29** — **Fix:** weak models could loop on tools (a "hi" spun the demo MCP echo tool to the iteration cap). Fixed: `general` agent is now tool-less (pure chat), the demo MCP server grants to no agent by default, and the agent loop forces a final answer after `MAX_TOOL_ROUNDS`. Verified live on NVIDIA (free): "hi" → clean answer in 2 iters; coding task → writes + runs a file. Added chat rename (double-click) + a background-tasks (jobs) panel.
- **2026-05-29** — **UI redesign**: integrated the Stitch "Agent//Core" design (warm-paper + terracotta, Geist/Source Serif/JetBrains Mono) via Tailwind; rebuilt all components (sidebar, chat + activity timeline, composer toggles, approval modal, Files/Rewind/Models right-panel tabs, dark mode) keeping all wiring. Cost-first model selector + model-scout.
- **2026-05-29** — Smoke test + Docker/run scripts + Langfuse forwarder; normalized `DATA_DIR` (sandbox robustness). Structured this tracker.
- **2026-05-29** — Per-agent sub-budgets, parallel subtask groups, per-turn streaming, persistent task queue, embedding memory, local tracing; `docs/PLACEHOLDERS.md`.
- **2026-05-29** — Cross-session memory, diff view.
- **2026-05-29** — Plan-first mode, real MCP adapter, critic/QA + retry, token streaming.
- **2026-05-29** — Permission modes, checkpoints/rewind, slash commands, export.
- **2026-05-29** — Platform (3 registries, dispatcher, supervisor, blackboard, layered security), persistence, WebSocket, React frontend.
- **2026-05-29** — Eval harness (roadmap #4).
