# HANDOFF — read this first

_The single entry point for a new chat. **Current state + next tasks live here**; durable
rules are in `CLAUDE.md`; full backlog in `docs/BACKLOG.md`; change history in `git log`.
For "what it can do" see `docs/CAPABILITIES.md`; "how it works" `docs/PROJECT_OVERVIEW.md`._

## ⚡ LATEST (2026-07-29) — "LOOP ENGINEERING" + reliability fixes + first real feature built on a live project

**7 commits to `main` (local only — NOT pushed). 447 pytest + web build clean.** Focus: make a
BATCH of features trustworthy (verify each before the next), fix two reliability rough edges the
work surfaced, then prove the whole thing by building + verifying a real feature on the OPPs Finder
project through Nikki.

### The headline — per-feature verify-and-retry ("loop engineering")
The sequential task-runner used to mark each item of a numbered list "done" the instant the agent
went quiet — no check. Now each feature is **built → gated → re-worked (up to 2 retries) → only
then verified**; a still-failing one is flagged `needs_attention` and the run CONTINUES
(flag-and-continue). "Done" now means *actually tested + reviewed*.
| Commit | What |
|---|---|
| `bc740c4` | **"Act, don't just plan" done-gate** — a build-intent run that changed ZERO files is re-prompted once to actually apply the edits (`_needs_act_retry`/`_workspace_sig`/`_ACT_NUDGE`, wired at all 5 build paths). |
| `9b1c57f` | **`evaluate_feature()`** — one public gate composing the existing act-check + deterministic pytest gate (`_verify_tests`) + QA critic (`_review`). No new verification logic. |
| `54ab7dc` | **`run_program` per-feature loop** (`server/taskrunner.py`) — build→evaluate→retry×2→`verified`/`needs_attention`; honest end-of-run scoreboard (only verified features count). |
| `c3a2661` | Web checklist shows the new states + a "try N / N tries" badge. |
| `18e69fe` | **Leaked tool-call markup never surfaces as the final answer** — the detector only matched a SINGLE full-width pipe, so DeepSeek's DOUBLE-pipe `<｜｜DSML｜｜tool_calls>` leaked out of a live LEAD run. Broadened the detector, made the stripper cut the whole trailing block (keeping prose), added a master-loop scrub net. |
| `826d1b1` + `1bacd00` | **Configurable verify-gate command** — `_verify_cmd()` resolves most-specific-first: per-project `.nikki/verify.txt` → global `AGENT_VERIFY_CMD` → default `python -m pytest -q`. Lets a project whose plain pytest can't run in the netless sandbox declare its own (e.g. the pure subset with `--noconftest`). |

### First real feature built on a live project (OPPs Finder), copy-safety proven
- **Copy-safety works** (`AGENT_LOCAL_ISOLATED=1`, `server/isolation.py`): Nikki built on a git
  CLONE of `C:\Project\OPPs Finder`, verified there, then the change was reviewed + applied to the
  real repo. The real folder was never touched mid-run.
- Built **two pure confidence helpers** via the loop (`points_to_next_tier`, `summarize_weights` +
  pure tests) — both **verified in-sandbox** (the gate really ran the tests: 39→41 passing) and
  applied to the real OPPs Finder repo (their commits `d034627` code, `34432f4` `.nikki/verify.txt`).
  Also corrected a **stale claim in OPPs Finder's `HANDOFF.md`** (it said Confidence Engine V2 wasn't
  wired — the code shows it IS: `confidence_calibration_job` → Redis weights → `twin_service`).

### Key constraint learned (don't re-discover)
Nikki's build sandbox is **network-isolated (`--network none`)**. So on an external project it can
only **auto-verify PURE/logic tests** — anything needing Postgres/Redis/a live service can be built
but only gets a *critic* review, not a real test gate. Point such a project's `.nikki/verify.txt` at
its pure subset (OPPs Finder's is set up this way). Running a DB-backed suite in-sandbox would need
a heavier setup (DB in the sandbox + relaxing network isolation) — deliberately NOT done.

### State right now
- **Server running** on `:8800` with `AGENT_LOCAL_ISOLATED=1` and **no** global `AGENT_VERIFY_CMD`
  (per-project file is the mechanism now). Restart with `.\run.ps1` picks up latest code.
- News/feeds WIP still uncommitted (unchanged). Nothing pushed (VM parked).
- **Next:** owner wants a planned set of **next OPPs Finder features** to build via the loop
  (prefer pure/logic ones so the gate can auto-verify them). See the grounded backlog planning.

## EARLIER (2026-07-23) — RENAMED TO "NIKKI" + big reliability + product/UI day (LOCAL focus)

**16 commits to `main` (local only — NOT pushed). 389 pytest + web build clean.** Big day: renamed
the platform, fixed the real memory bug, added voice/task-runner/folder-mode, and a premium UI pass.
The local dev DB was **wiped to a clean slate** (backups `data/app.db.bak-cleanslate` +
`.bak-precleanup`; keys/settings kept). Verify visually by `.\run.ps1` + hard-refresh (Ctrl+Shift+R)
— screenshots time out on this box, so everything below was verified via tests + API/live WS.

### Reliability / correctness
| Commit | What |
|---|---|
| `40d3784` | **Memory-bleed ROOT CAUSE fixed.** It was NOT episodic recall — it was **fact-extraction saving a one-off build's spec as GLOBAL facts** (`project_type: Habit Tracker`…), injected into every chat → unrelated chats rebuilt it. Fix: facts scoped to the run, never global. Owner's isolation model (**standalone chats isolated; same-project chats share**): recall hard-limited to scope + distinctive-word relevance gate + write-time self-consistency (don't store off-topic/parroted/QA-failed answers) + stricter fact prompt/signal-gate. Also **`/clear`** + **`/compact`** commands (non-destructive context-reset boundary). |
| `ced0391` | **Mic-tolerant reads + junk-dir hygiene.** `read_file` auto-reads the closest real file when the name is slightly off (mic "handoff.in" → `HANDOFF.md`) with a note; ambiguous → lists candidates; edit/parse suggest "did you mean". `list_files`/`glob`/`grep` + roadmap walker now hide `.git`/`node_modules`/… (was wasting reads on git internals). |
| `ad71e86` | **Reliable "what's left" roadmap + `/todo`.** Roadmap now MERGES/PRESERVES todos (a later turn can't wipe it; phased-build path captures todos too); new `/todo` lists open items on demand. |
| `04032f6` | **Context meter + model name** in the run summary (`context` event = this turn's input size vs the ~24K working budget; model derived from assign/route). |
| `3bd8bab` | **Sequential task-runner** (`server/taskrunner.py`): a numbered/bulleted list (≥2 items) runs one-by-one with a live checklist (`program` event), shared Budget, isolated errors. Per-task prompt insists on real tool use (fixed a cheap-model narrate-don't-act miss). |
| `2fceaee` | **Vision/uncatalogued spend now counted** via provider `usage.estimated_cost` (litellm lacked the DeepInfra VLM price → logged $0). ~$0.0002/screenshot. |

### Product / UI (feels premium now)
| Commit | What |
|---|---|
| `1704406` | **Renamed the platform to "Nikki"** (tab/login/sidebar wordmark; infra names untouched). |
| `1929f46`+`ea8ee09` | **Voice input** — mic button → **Whisper** speech-to-text (works with the existing DeepInfra key; provider-agnostic via `STT_MODEL`/`GROQ_API_KEY`, endpoint `server/api/voice.py`). Live "Listening…" equalizer + "Transcribing…" feedback. Voice output (talk-back) deferred. |
| `0a57adb` | **Serif replies (Newsreader) + clean sans UI (Inter) + spinning Nikki mark** while thinking. |
| `10e21df` | **Resizable Workspace panel** (drag left edge 300–760px, persisted via `--panel-w`). |
| `11f4f0d` | **Premium artifact canvas** (expand, Esc to close) + **CSV/TSV render as tables**. |
| `79537f2` | **"Work on a folder"** — the `+` is now a menu: Attach file · Work on a folder (binds a project to a local folder, cwd-style) · **paste a screenshot** into the box. |
| `c5d8dce` | **UI polish pass** — keyboard **shortcuts overlay** (press `?`; new `⌘⇧O`/`⌘\`), **accent-color picker** (6 presets, Settings → General, via `--accent` var), richer prose (blockquotes/tables/hr), modal pop-in motion. |
| `499d1b1` | Settings: Schedules pre-fills a valid spec on type change. |

### Next (owner's call) — nothing blocking; app boots clean, local mode on
1. **Hands-on visual pass** on the clean slate: rename, serif replies, spinning mark, mic (`?` for
   shortcuts), accent picker, resizable panel, `+`→Work-on-a-folder, paste-a-screenshot, a numbered
   task list → checklist, `/clear` `/compact` `/todo`, fuzzy filename read, context %/model in summary.
2. **Memory** — owner wants a transparent, editable **markdown knowledge-base** layered on the existing
   embedding recall (my recommendation: hybrid, not a graph rewrite). Deep Research mode also of interest.
3. **Voice output (TTS)**, per-step QA verification for the task-runner, connectors — deferred.
4. **News/feeds WIP** (`tools/feeds.py`, `config/feeds.yaml`, `config/agents.yaml` edits, `AGENTS.md`,
   `docs/NEWS_AGENTS_PLAN.md`, `docs/RELIABILITY_PLAN.md`, `tests/test_feeds.py`) still uncommitted —
   decide finish/branch/drop. `tasks.db` + synced `skills/` also untracked. Nothing pushed yet.

## EARLIER (2026-07-17→20) — FULL E2E TEST ROUND (VM + LOCAL), 3 more live-found fixes shipped, reliability verdict 8/10

**Everything below is MERGED + DEPLOYED** (PRs #17–#20 all merged to `main`; VM auto-deployed).
Full test report artifact: https://claude.ai/code/artifact/5815ca6e-3a7b-41f2-b4ba-cf44ed44841b

### Live-production e2e (VM) — 19/19 checks passed after fixes
Drove the deployed app over the real WS + SSH'd the VM (owner granted `.claude/settings.local.json`
allow-rules for `ssh ubuntu@100.89.151.102` + `gh pr create/merge/view`; SSH key at
`C:\Users\gaura\Downloads\oracle keys\ssh-key-2026-06-14.key`, wired via `~/.ssh/config`).
Three NEW bugs found live, each fixed→PR→CI→merged→redeployed→re-verified same day:
| PR | Bug found live |
|---|---|
| #18 | Dispatcher sent "clone this repo" to the **frontend** agent → deterministic repo routing (`_REPO_STRONG` in `core/agents.py`) |
| #19 | Agents ran `git clone` inside the **netless sandbox** (19 wasted calls) → `run_bash` blocks network-git verbs, redirects to host-side `git_clone`/`git_push` (`core/tools.py:_NET_GIT`) |
| #20 | **git repo-discovery walked UP out of the workspace** — `git_log` in a fresh session returned the APP's own commits (a stray commit would land in the app repo!) → `GIT_CEILING_DIRECTORIES` in `tools/github.py:_git` |
Also fixed on the VM directly: `.env` had a literal `ghp_your_token_here` placeholder overriding
the real GITHUB_TOKEN (removed); funnel restored + made reboot-proof (`agentfunnel.service`
installed + enabled); `AGENT_BASH_DOCKER_NETWORK=none→bridge`. VM funnel layout: the tailnet
hostname is now `apps` — the agent app is PUBLIC at `https://apps.tail1d9a60.ts.net` (:443→8800);
ports :8443 and :10000 belong to the owner's OTHER apps (3000/8000/8801/8802) — don't touch.

### Local e2e battery — 23/23 external checks, day-to-day verdict **8/10**
Owner pivoted: **VM parked, focus is LOCAL** (local folders / repos / attached reports).
Battery is preserved as **`scripts/e2e_local.py`** (self-seeding; usage in its docstring):
fixed planted bugs IN PLACE in a real local folder (external pytest 4/4, tests untouched,
$0.0016), multi-turn feature-add (5/5), attached-CSV analysis (3/3 numbers exact), habit-tracker
build with check_page self-verify ($0.011), live web research, graceful missing-file handling,
local-root escape + traversal rejected. Latency: simple 10–40s, folder-fix ~2min, build ~5min.
A day of heavy use ≈ $0.05–0.20.

### ⚠️ TOP OPEN BUG — "memory bleed" (found live, NOT yet fixed)
Episodic memory recall injected a **just-finished unrelated chat** (habit-tracker build) into a
fresh session; a cheap model **parroted the recalled content as its answer** (user asked about a
missing xlsx, got "Perfect! The habit tracker is fully functional…"), and the wrong exchange was
then STORED BACK into memory (pollution compounds). Nondeterministic (~1/10; a stronger model
answered honestly on repro). **Fix direction:** relevance-gate episodic recall in
`server/memory.py` (similarity threshold + don't recall same-day unrelated sessions + cap
injected items), and consider not storing exchanges whose answer the critic failed. Scenario F
in `scripts/e2e_local.py` has an off-topic detector to regression-test this.

### Pending (ordered) — next session starts here
1. **Fix the memory bleed** (above) — top reliability item for daily local use.
2. **VM GITHUB_TOKEN is INVALID (401)** — owner must mint a fine-grained PAT with write access
   to chosen repos (public-only tokens are read-only!), paste cleanly (the old line had a stray
   quote + CR from a Windows paste), restart agentcore. Until then the deployed repo-engineer
   can clone/read but NOT push/PR. (Local has no GITHUB_TOKEN either — same fix if needed locally.)
3. **PR-completion verifier** — agent occasionally pushes but skips `create_pull_request`
   (seen once); if the task asked for a PR, check one exists before finishing.
4. **GitHub-token status card** in Settings (+ startup .env hygiene warnings: placeholders,
   stray quotes, CR line-endings — both real incidents this round).
5. **Health-gated deploy** — deploys briefly 502 the public URL; workflow should curl
   /api/health after restart and fail loudly.
6. Owner cleanup: delete throwaway repo `Nikethan16/repo-engineer-e2e` (+PR #1), rotate the
   fine-grained PAT that was pasted into chat, decide fate of local news/feeds WIP (still
   uncommitted, untouched), `tasks.db` untracked in repo root.
7. Roadmap (owner interest, in order): repo dashboard UI · vision input (Qwen-VL, ~$0.001/img)
   · Telegram approvals (bot creds already on VM) · scheduled repo jobs · PR-review agent ·
   desktop app (Tauri shell) · zero-downtime deploys.

### Context for the next chat (don't re-discover)
- **Local mode is now ON by default**: `AGENT_LOCAL_MODE=1` + `AGENT_LOCAL_ROOT=C:/Project` were
  added to the local `.env` (2026-07-20), so a plain `.\run.ps1` → http://localhost:8800 has the
  folder picker. Sample project at `C:\Project\e2e_sample_app` (project "e2e local app" in the
  local DB, plus e2e build/report sessions with viewable artifacts).
- Push with `git -c credential.helper= -c credential.helper='!gh auth git-credential' push …`
  (plain push hangs on a credential prompt). `gh` is authed as Nikethan16 (no `delete_repo` scope).
- The permission allow-list lives in `.claude/settings.local.json` (ssh to the VM + gh pr cmds).
- Reliability weak spots to keep in mind: memory bleed (above) + cheap-model tool-choice drift
  (favors run_bash over dedicated tools — now deterministically guarded for git; same pattern
  may apply elsewhere).

## EARLIER (2026-07-16/17) — streaming, folder picker, model-health UI, funnel unit, + 2 repo-engineer bug fixes (MERGED via PR #17)

Continues the phased-build/routing work (`4bec8e5`). **7 commits this session, all green (330 pytest + web build clean).** Each verified live before commit.

| Commit | What |
|---|---|
| `09be3c3` | Stream the model's **thinking** (reasoning_content) live + show **code as it's written**. New `thinking` event; `on_reasoning` in `core/llm.py` stream fns; collapsible "thought process" + live "writing <file>" panels in `web/`. Verified on deepseek-v4-pro (926 thinking events streamed, separate from the answer). |
| `8a6ae7a` | **Folder picker** for local-folder projects — `localmode.browse()` + `GET /api/local/browse` (confined to `AGENT_LOCAL_ROOT`) + a directory navigator in `NewProjectModal`. Works on the headless VM (no native OS dialog). |
| `071d305` | **Model reliability + degraded** column in the Health panel (`metrics.summary` now carries `reliability`/`degraded`, computed OUTSIDE the lock — reliability() re-acquires it and the Lock isn't re-entrant). |
| `3d18642` | **Funnel systemd unit** — `deploy/agentfunnel.service` re-publishes the Tailscale funnel every boot (fixes "the VM URL died after reboot"). `deploy/README.md` + SETUP_GUIDE Step H. |
| `2f79c1a` | **BUG FIX**: after a token-authed clone, `git_push` re-injected the token → `oauth2:..@oauth2:..@` malformed URL → *every push failed*. Clone now stores a clean origin; push strips existing creds first. |
| `ce058b5` | Regression tests (`_auth_url`, `localmode.browse`, `metrics` reliability) + extracted `_auth_url` helper. |
| `adf11b2` | **BUG FIX**: `git_clone` cloned into a SUBDIR so every later git tool failed ("not a git repository"); now clones into the workspace root when empty (matches project repo-mode). |

**Repo-engineer validated end-to-end** — both bugs above were found by this test. The real LLM agent ran clone → branch → write files → **run tests** → commit → push → open a real PR autonomously ($0.001, 16s; PR API-confirmed open). ⚠️ Gotcha: on one run the agent pushed the branch but drifted into `run_bash` instead of calling `create_pull_request` — a nondeterministic *behavior* wobble, not a tool bug. Watch for it if you lean on repo mode.

### VM steps still needed (owner — the agent can't reach the VM)
1. **Repo mode live:** add `GITHUB_TOKEN` to the VM `.env` → `sudo systemctl restart agentcore`. The two fixes above mean clone→push→PR now actually works.
2. **Funnel auto-start:** `sudo cp deploy/agentfunnel.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now agentfunnel`.
3. **Docker sandbox** (unlocks `run_bash` + live frontend-verify): confirm `agent-verify:latest` on the VM, set `AGENT_BASH_DOCKER_IMAGE` + `AGENT_BASH_DOCKER_NETWORK=bridge`, unset `AGENT_DISABLE_BASH`.

### Cleanup / gotchas
- **Throwaway test repo `Nikethan16/repo-engineer-e2e` still exists** (PR #1 open + a `feature/farewell` branch). The `gh` token lacks `delete_repo` — delete it on GitHub, or `gh auth refresh -s delete_repo` and the agent will remove it.
- **`gh` CLI IS installed & authed now** (accounts `Nikethan16` [active] + `Nikethan-cbc`) — the older "gh not installed" note below is stale.
- **News/feeds WIP is still local/uncommitted** (owner's, deferred): `config/agents.yaml` mods, `tools/feeds.py`, `config/feeds.yaml`, `tests/test_feeds.py`, WIP hunks in `tools/github.py`+`tools/__init__.py`, `AGENTS.md`. This session's commits used filtered patches to avoid touching them.
- Local run: `.\run.ps1` → http://localhost:8800. Thinking streams live on reasoning models (deepseek-v4-pro).

## ⚡ EARLIER (2026-07-13/14) — 7 features shipped to `main` (DEPLOYED) + a UI redesign on branch `ui-redesign` (NOT merged)

**Read this whole section before touching anything.** Two separate bodies of work this session:

### A) Shipped to `main` and LIVE on the VM (7 commits, `75aabf5..2548918`, CI + Deploy both green)
| Commit | What |
|---|---|
| `3c94642` | **Parallel research fan-out** — the staged pipeline's research stage now splits into independent sub-questions and runs them concurrently (`_split_research` + `_run_agents_parallel` in `core/orchestrator.py`). Dependent stages stay sequential (A/B-proven). Worker threads re-bind workspace/budget/span. |
| `d946208` | **Disk janitor** (`scripts/cleanup.py`) — prunes ORPHANED + AGED traces/checkpoints. Server runs the safe sweep at startup (`AGENT_DISABLE_JANITOR=1` opts out). `--workspaces`/`--docker` are opt-in. `docker/build-verify-image.sh` now prunes the dangling image. |
| `4e1991f` + `a63a9a5` | **Composer: inline Mode · Model · Effort.** Effort (Low/Default/High) scales budget+iterations and flips the QA default (in `server/api/ws.py`). Model pin = run-scoped ContextVar in `core/registry.py` (prepends to every chain, routing stays as fallback, **excluded from `classify`**); parallel workers re-bind it. `/api/models` now flags `available`. |
| `54aab3c` | **Project from a Git repo** — `POST /api/projects` accepts `repo_url`+`branch`; clones into the project's shared workspace (`tools/github.clone_into`, SSRF-guarded). `GET /api/projects/{id}/repo` = branch/changes/commits. |
| `0a0ec33` | **Multi-file HTML preview** — `server/htmlbundle.py` inlines local CSS/JS/images so a multi-file app renders in the sandboxed `srcDoc` iframe. `GET /api/sessions/{id}/preview`. |
| `2548918` | **Local-folder mode** — bind a project to a REAL folder (`server/localmode.py`). Gated by `AGENT_LOCAL_MODE=1` + confined to `AGENT_LOCAL_ROOT` (default: home), realpath-checked, re-validated on every workspace lookup. **The VM never sets these — keep it that way.** |

Validated: **297 pytest + 170 smoke green**, web builds, each feature verified live before commit.

### B) UI REDESIGN — branch `ui-redesign`, 5 commits, **NOT pushed, NOT merged** (`main` is clean/deployed)
`2c7909c` warm-cream theme + clay accent + clean-sans greeting · `f39523f` docked Workspace panel (project files + usage chart) · `6451dbe` sidebar nav + Pinned/Recents + clean panel · `836c886` ChatGPT-style nav (drop Home/Artifacts, expandable Projects, Scheduled view) · `7c76859` Scheduled tasks page + Project home with charts.

**The owner's LOCKED design direction — do not re-litigate:**
- **Warm cream canvas + clay accent, clean sans. NO serif, NO blue/indigo.** (An earlier iris/graphite proposal was rejected outright.)
- **No suggestion chips** on the welcome screen. **No "Home"** and **no "Artifacts"** nav item. No ⌘K badge on New chat.
- Settings + Dark mode live **in the profile menu** (account footer), not the nav.
- Right panel = a single **Workspace** (project files + usage chart), **no visible tab bar** (Rewind/Skills/Tasks/Trace live behind a ⋯ menu).
- Reference the owner kept pointing at: ChatGPT/Claude desktop sidebars (clean, expandable Projects).

### Next tasks (owner's latest feedback — NONE of these are built yet)
1. **Vision model** — owner wants **screenshot understanding** (vision INPUT only; NOT image generation). Agreed pick: **Qwen-VL on DeepInfra**, firing **only when an image is attached** (text tasks stay on the current fleet). ⚠️ **Owner asked for a COST estimate first and it was never answered** — answer that before wiring.
2. **Purge stale dev test projects** — the local dev DB is full of test projects (`only-this`, `capped`, `budget-test`, `overview-proj`, `status`, `uncapped`) that clutter the sidebar. Local dev data only — NOT on prod.
3. **Per-chat ⋯ menu** — replace the hover star/close icons with a proper menu: **Rename · Pin · Move to project/folder · Delete**.
4. **Project → Folders → Chats hierarchy** — folders under a project, chats under folders. Needs a data-model change (a `Folder` table or `session.folder_id` + additive migration in `server/db.py:_migrate`), API, and sidebar UI. Biggest remaining item.
5. **New-project popup** — owner reported it opening "in the sidebar"; `NewProjectModal` already renders centered — verify against what they actually saw before changing.
6. **Merge the redesign** — owner reviews `ui-redesign`, then merge → `main` → auto-deploy.

### Gotchas (cost real time this session)
- **The browser screenshot API times out locally.** Verify UI via `javascript_tool` computed styles / `innerText`, not screenshots.
- **Section labels are CSS-uppercased** (`text-transform: uppercase`) — case-sensitive regex on `innerText` gives **false negatives** ("PROJECTS" not "Projects"). Bit me twice.
- **Don't half-build and stop to ask.** The owner locked the design and got (rightly) frustrated when work landed in partial increments with questions attached. Build the agreed thing fully, then show it.
- Local run: `AGENT_DISABLE_JANITOR=1 .venv/Scripts/python.exe -m uvicorn server.app:app --port 8800 --host 127.0.0.1` (no login locally → account footer reads "Account").
- The VM's verify Docker image **was rebuilt** by the owner this session — that item is done.

## (2026-07-12) — full E2E test round, 13 fixes, staged multi-agent pipeline (branch `claude/commands-and-lsp`, MERGED to `main`)
Ran a **full end-to-end test round** (live UI + engine-level, on real seeded repos), found 11
issues, and fixed **all** of them plus added a multi-agent pipeline. **~16 commits, all
validated: 260 pytest + 170 smoke green, `tsc` clean, `npm build` clean; doc-gen + the new
pipeline proven live on real repos.** Full write-up: `docs/TEST_REPORT_2026-07-12.md`.

**Fixes shipped:**
- **Doc/Office generation now works in the sandbox** — baked the doc libs (openpyxl, python-docx,
  pptx, reportlab, pypdf, pdfplumber, markitdown, Pillow) into `docker/verify.Dockerfile`, and
  aliased `/workspace`→`/ws`. *Proven live: agent produced a real `planets.xlsx`.*
- **Human approval gate restored** — the security-manager review no longer fail-closes on an
  empty/garbled model reply; an `[infra]` failure falls through to the human card (`server/approvals.py`).
- **Policy** matches action rules against commands, not written file **content** (a doc that says
  "deploy" no longer gets escalated) (`core/policy.py`).
- **Dead NIM ids removed** (`z-ai/glm-5.1` 410, `deepseek-v4-flash` 404) — the cost-first picker
  was *selecting* the dead GLM (`config/models.yaml`).
- **Reliability:** a 429 benches a model for 10 min (not re-probed each minute); research free-floor
  leads with Nemotron-Super before the loopy qwen (`core/llm.py`, `config/models.yaml`).
- **Skill selection tightened:** `web-frontend` intent-gated; heavy doc-format skills only auto-load
  for agents that can run them (a research step was staging ~1MB of xlsx schemas) (`core/skills.py`).
- **Polish:** UNVERIFIED banner only when the agent has run_bash; sub-cent budget-cap display;
  run_bash cwd hint; dogfood Windows fixes; flaky smoke `_facts[0]` guard.
- **`/commands`** was a stale-build artifact, not a code bug (source was correct; rebuilt `web/dist`).

**NEW — staged multi-agent pipeline (`core/orchestrator.py`):** a *research + build* task now runs
a deterministic manager: **research → architect (plan) → coder (implement+verify) → code-reviewer**,
with each stage's artifact (`findings.md`, `design.md`) passed forward via the blackboard + workspace.
Triggered by `_wants_pipeline` (research signal AND build signal). Pure coding stays single-agent
(the speed-fix); multi-domain coordination without research still uses the LEAD master loop.
*Proven live: 4 specialists, real handoffs, tests pass, $0.008.*

**Dropped** the image-generation agent (no image/vision requirement now; re-enable = restore one
YAML block + `image_model:` + key).

**⚠️ REQUIRED VM steps after this deploy** (auto-deploy does reset→pip→npm build→restart, NOT these):
1. **Rebuild the verify Docker image** so doc-gen + the `/workspace` alias work on the VM:
   `./docker/build-verify-image.sh` (it now includes the doc libs). Without this, doc generation
   still fails on the VM.
2. Confirm `DEEPSEEK_API_KEY` + `DEEPINFRA_API_KEY` in the server `.env` (the pipeline works on the
   free floor without them, but the paid fleet is faster/better). Gemini free quota was exhausted
   during testing — a second `GEMINI_API_KEY` reduces latency.

**Next tasks:** (1) large-repo **map step** — the architect reads *all* files today, which won't
scale to big codebases; add a file-tree/symbol map or lightweight index. (2) Semantic skill
selection + more skills (debug/refactor/git). (3) **Live-UI re-verify** the approval card,
`/commands` menu, and doc-gen (the preview pane was broken this session, so those three are proven
by unit/E2E but not re-driven through the real app). (4) `python -m evals` A/B on the routing choices.

## ⚡ (2026-07-11, pt.2) — `/commands`, real LSP, UI redesign, dogfood (folded into the 2026-07-12 merge)
Closed the two remaining OpenCode-parity gaps, shipped the UI redesign + polish, and added
the self-engineering dogfood harness. **13 commits, all validated: 258 pytest + 170 smoke
green, `tsc --noEmit` clean, `npm build` clean.** Not merged to `main` (held for the owner).
Built on a fresh Linux clone with **no keys/Docker**, so the live dogfood run + eval A/B still
need the owner's laptop/VM (everything else is validated).

1. **User-authored `/commands`** (`core/commands.py`, `config/commands/`, `server/api/commands.py`,
   wired in `server/chat.py`). `.md` templates → `/name`; substitutions `$ARGUMENTS`/`$1..$9`,
   `@file` (sandboxed read), `` !`shell` `` (via Docker `run_bash`, no-ops without an image).
   Args inserted literally, never re-scanned (no injection). Frontend: `/` menu in the composer,
   ⌘K palette entries (`GET /api/commands`).
2. **Real LSP / diagnostics** (`core/lint.py`) — a `diagnostics` tool (granted to the 5 code
   agents) + the post-edit hook use **ruff** when present, falling back to in-process
   pyflakes+compile. Static-only, workspace-confined. `ruff` added to `requirements.txt`.
3. **UI redesign + polish** (mockup: https://claude.ai/code/artifact/73a43488-7a32-4150-a376-ff02aed3c53d):
   chat list grouped-by-recency + auto-titled (`db._derive_title`) with a metadata subline;
   run-summary header (verdict pill + metric columns); right panel split Changed-this-run
   (+/- deltas) vs Context; **Health** panel status pill + summary tiles + cache meters;
   **Schedules** panel summary + status pills; **mobile pass** (Settings modal stacks, composer
   popovers capped — no overflow at 320/375px). Visually verified with seeded data.
4. **Dogfood harness** (`scripts/dogfood.py` + `run_dogfood.ps1`) — see "Run the dogfood" below.
5. **Fixed 2 pre-existing latent `tsc` bugs**: duplicate `setRouting` in `api.ts` (split into
   `setRouting`/`setFleetRouting`); `FilesPanel` expand-view missing `<Body id>`. `tsc` now clean.

**To ship:** merge `claude/commands-and-lsp` → `main` (auto-deploys). All keyless except the
LSP tool wants `ruff` (`pip install -r requirements.txt`).

### Run the dogfood (self-engineering test) — LOCAL, needs keys
On the laptop/VM (keys in `.env`, from the repo root):
```
git pull --ff-only
.\run_dogfood.ps1                 # built-in calc demo: add multiply() + test, run it, PASS/FAIL
.\run_dogfood.ps1 -Dir .\yourproj -Task "write pytest tests for X and make them pass"
.\run_dogfood.ps1 -SeedOnly       # prepare only, no model calls (sanity)
.\run_dogfood.ps1 -Force          # skip the model pre-check
```
It resolves the real model chains, runs the agent, reports which files changed + a pytest
pass/fail. `-Dir` copies your project first (non-destructive; `-InPlace` to edit directly).
**Gotchas we hit:** the venv was bound to the old `C:\` path after moving the repo to `D:\`
(recreate with `python -m venv .venv` + `pip install -r requirements.txt`; the `.ps1` uses the
venv python so `pip.exe` launcher breakage doesn't matter). A `410 Gone` in a run = a **stale
NIM/model id** — run `python -m scripts.verify_models` and fix ids in `config/models.yaml`.
**Classify leads with Gemini**, so `GEMINI_API_KEY` must be in `.env` or classify falls to a
(possibly stale) NIM floor id.

## LATEST (2026-07-11, pt.1) — cost/quality + paid fleet + Skills Hub + UI flow (branch `claude/cost-quality-config`, MERGED via PR #14)
Big multi-part session on branch **`claude/cost-quality-config`** — **20 commits, all
validated (230 pytest + 170 smoke green, frontend builds).** PUSHED to origin so it can be
pulled on another machine; **NOT merged to `main`** (main auto-deploys → held for the owner).
**To go live: merge to `main` → auto-deploy, then do the VM steps in "Next tasks".**

**Paid model fleet (BYOK, fit→reliability→cost).** Finalized 2-key paid fleet behind
`requires_env`, cost-first routing (`config/models.yaml`):
- **DeepSeek direct** (`DEEPSEEK_API_KEY`): V4-Pro plans/lead, V4-Flash builds/chat — call
  DIRECT so its automatic prompt cache stays warm (75-85% cache seen live → near-free builds).
- **DeepInfra** (`DEEPINFRA_API_KEY`): GLM-5.1 review/QA, Nemotron-Super research, Qwen3-Coder
  data, Qwen3-VL vision. **Model IDs were verified live** — the guessed ids were wrong; correct
  ones are in `models.yaml` (e.g. `deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B`,
  `deepinfra/Qwen/Qwen3-Coder-480B-A35B-Instruct-Turbo`, `deepinfra/zai-org/GLM-5.1`).
- **GLM 4.6→5.1** chosen after a live bake-off (5.1 = cheapest/fewest-tokens/verified; 5.2
  slower but more defensive; both catalogued + selectable in the UI routing editor).
- Every chain lists paid leads first, then the FULL free NIM/Gemini floor → **keyless = exact
  old behavior**. NVIDIA (4 pooled keys) is the free fallback floor.
- **Rollout tool:** `python -m scripts.verify_models` (one cheap probe per keyed model — run
  it whenever a key lands; catalogs rename models within weeks). `docs/MODEL_PLAN.md` = the ref.

**UI-editable routing** (`RoutingEditor.tsx` under Settings › Models › Routing) — pick the
model chain per use case; persists to `data/routing.json` (merged over models.yaml, survives
deploys). No hardcoded models. Backend: `registry.set_routing/reset_routing`, `/api/models/routing`.

**Reliability/correctness fixes** (live-testing found these): router now has **chat/general**
task types (a factual Q was misrouted to tier-2 coding → burned 20k tokens; fixed); tier-3
coding **repins to `coder`** if the dispatcher picks a non-builder; the run's **model display
now shows the real task-aware model** (was tier-cheapest); **prompt-cache hits surfaced**
(`prompt_cache_hit_tokens` → run-summary "% cached" + Health panel); sampling overlay + per-
model timeout now applied on the **streaming** paths too.

**Skills Hub + security** (`core/skill_sync.py`, `core/skill_scan.py`): sync skills from an
**allowlisted** GitHub repo (`config/skill_sources.yaml` → anthropics/skills), bounded +
path-safe + provenance-tracked; each lands **DISABLED + static-security-scanned** (exec/eval/
subprocess/.env/credential/network → safe/caution/risky); **enabling a "risky" skill is
BLOCKED without override**. UI: Skills tab with add-from-GitHub, risk badges, scan findings,
override. Verified live (synced webapp-testing/mcp-builder/skill-creator → all disabled+risky).

**OpenCode parity** (it's MIT — gap analysis in `docs/OPENCODE_GAP.md`): `apply_patch`
(multi-file unified diff, granted to the 5 code agents), opt-in formatter-on-edit
(`AGENT_FORMAT_ON_EDIT=1`, black), post-edit pyflakes lint, AGENTS.md project-notes injection
(wrapped as untrusted data), ported OpenCode prompt-behavior overlays, and the **`@file`
mention** picker in the composer. **Still missing (next batch): user `/commands`, real LSP.**

**UI run-flow redesign** (`Chat.tsx`): a run renders as **Plan → Steps → Verify** with
collapsible step cards (agent + summary + tools/output) instead of one long bubble. A
[mockups artifact](https://claude.ai/code/artifact/2c6dbd22-3b10-4a8d-8b91-b74c353056e7) shows
the full intended direction; only the run-flow + @file are built so far.

**New scripts:** `verify_models.py`, `sync_skills.py`, `perf_battery.py` (live task battery +
GLM bake-off). **New docs:** `MODEL_PLAN.md`, `OPENCODE_GAP.md`. **New optional env:**
`AGENT_FORMAT_ON_EDIT`, `AGENT_BASH_DOCKER_IMAGE` (now in local .env).

**🟡 LOCAL-ONLY work NOT on the branch (won't transfer to another laptop unless committed):**
`config/agents.yaml` (news-agents: finance-news, tech-scout), `tools/feeds.py`,
`config/feeds.yaml`, `tests/test_feeds.py`, `tools/__init__.py`+`tools/github.py` mods,
`AGENTS.md`, `docs/NEWS_AGENTS_PLAN.md`, `docs/RELIABILITY_PLAN.md`. Owner chose to keep these
local (news-agents deferred). Synced skills (`skills/mcp-builder` etc.) are gitignored — re-sync
on the other laptop via the Skills tab / `python -m scripts.sync_skills`.

**Keys:** `DEEPSEEK_API_KEY` + `DEEPINFRA_API_KEY` are now in the **local** `.env` (live +
verified). On the other laptop / the VM they must be added there too. Langfuse: **not needed**
(local traces + Health + Usage cover it).

**Local Docker sandbox:** `agent-verify:latest` built on this dev laptop
(`./docker/build-verify-image.sh`); `AGENT_BASH_DOCKER_IMAGE=agent-verify:latest` in local .env.
On a fresh laptop you must rebuild that image.

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
  the app — see "Security follow-ups" below); **nightly backups** via cron
  (`scripts/backup.py --keep 14`).
- **Run/test:** local run `.\run.ps1` → http://localhost:8800. **136 pytest pass (+2 skipped:
  symlink tests need OS symlink perm)** (`python -m pytest tests/ -v`; `pytest` lives in
  `.venv`). Smoke **171/171** (`scripts\smoke_test.py`). Rebuild UI after frontend changes:
  `npm --prefix web run build`.
- **Diagnostics**: `python3 scripts/inspect_run.py --list` / `<session_id>` — read-only dump
  of a run's full event timeline, span-tree (cost/tokens/duration), generated workspace files,
  and last stored message. Use this whenever asked "what did a run actually do."

## Last session (2026-06-20, pt. 2) — Phase 2 + app hardening (branch `claude/phase2-and-hardening`, stacked on the port branch)
Broad "make the whole app better" pass. 6 commits, each tested. **pytest 130/130, smoke 171/171.**
Not merged; no PR yet. Builds on `claude/coding-engine-port`.
1. **Phase 2 — coding engine finished:** within-run **context compaction** (`core/agent.py:_compact_messages`,
   both loops, summarizes old turns at 80% of the context budget, preserves tool-sequence
   validity) — the ROOT fix for orch #2. Plus a **post-edit syntax verifier** (in-process
   `.py`/`.json`/`.yaml` check appended to write/edit results; safe offline LSP stand-in).
2. **Security:** **encrypt API keys at rest** — `AGENT_SECRET_KEY` Fernet-encrypts
   `data/keys.json` (`core/keypool.py`), backward-compatible (legacy plaintext still loads).
   (Off-site backups were already supported via `BACKUP_UPLOAD_CMD` — just set it.)
3. **Capability:** **per-project budgets** — `Project.budget_usd` cap, enforced + tracked per
   project; `GET /api/projects/{id}/spend`. Additive migrations (spend.project_id, project.budget_usd).
4. **UI:** mobile **drawer overflow fix** (sidebar/artifacts panel no longer overflow narrow
   phones; verified 320/375px via the preview tools, no console errors).
6. **Usage & Cost dashboard:** new Settings tab (today vs cap, all-time, 14-day spend bars,
   per-project table) backed by `spend.overview()` + `GET /api/spend/overview`; verified live.
7. **Post-build audit + optimizations** (3 commits): subsystem review (core loops/tools/server/
   model layer) → fixed per-turn full-table scans (spend now SQL-aggregated; facts/rules
   scope-filtered in SQL; `context_budget` O(catalog)), missing migration indexes,
   parallel-delegation exception isolation, resilient compaction (fallback chain), keystore
   data-loss guards (refuse-overwrite + atomic write), and grep/glob symlink containment.
   **Deferred (tracked in BACKLOG "Post-build audit"):** circuit-breaker sensitivity tuning,
   abandoned-timeout-future bounding — left as-is to avoid regressing the documented hang fixes.
5. **New optional env vars:** `AGENT_SECRET_KEY` (key encryption), `AGENT_COMPACT`/`AGENT_COMPACT_RATIO`/
   `AGENT_COMPACT_KEEP` (compaction), `AGENT_POSTEDIT_VERIFY` (syntax verifier). All default-safe.

## Earlier session (2026-06-20) — absorb OpenCode's coding-engine design (branch `claude/coding-engine-port`)
Reimplemented the best of OpenCode (MIT) in our own Python — **no OpenCode runtime
dependency** (attribution in `THIRD_PARTY.md`). 11 commits, each with tests. **pytest 111/111,
smoke 171/171.** Not yet merged to `main` (no PR opened — awaiting owner).
1. **Tool reliability port:** fuzzy `edit_file` (5-strategy cascade, whitespace/indentation
   tolerant, REFUSES low-confidence matches); `read_file` numbered lines + offset/limit + caps;
   new pure-Python sandboxed `grep`/`glob` code-search tools (granted to the coding agents);
   tool-argument schema validation before execution (`toolbelt.validate_args` → re-issue on
   bad args).
2. **All 7 orchestration issues fixed** (see `docs/BACKLOG.md` for the per-issue mapping):
   leaked raw tool-call markup (#1), research death-spiral (#2), 7× re-plan (#3), tier/agent
   cost mismatch (#4), skill over-trigger (#5), workspace collisions (#6, behind
   `AGENT_TASK_SUBWORKSPACE`, off by default), `/ws` path mismatch (#7).
   - **#2 is a MITIGATION, not a root fix.** The near-cap synthesis nudge + forced
     `_finalize_from_board` stop the *symptom* (raw text surfaced as "final" at the cap). The
     *root cause* is context bloat reaching the cap — the real fix is **within-run compaction,
     scheduled as PHASE 2** in `docs/BACKLOG.md`.
3. **New optional env vars:** `AGENT_TASK_SUBWORKSPACE` (off), `AGENT_READ_MAX_LINES` (2000),
   `AGENT_READ_MAX_BYTES` (51200). Note: `pytest` was installed into `.venv` to run the suite.

## Earlier session (2026-06-18) — observability tool, real-run deep-dive, public exposure
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

## Next tasks (immediate — the `claude/cost-quality-config` branch is the active work)
1. **Ship the branch to prod** *(owner decision — main auto-deploys)*: merge
   `claude/cost-quality-config` → `main`. THEN on the VM: add `DEEPSEEK_API_KEY` +
   `DEEPINFRA_API_KEY` to server `.env`; `sudo systemctl restart agentcore`; run
   `python -m scripts.verify_models` (confirm the paid model ids resolve — they were verified
   locally but re-check on the VM); ensure `agent-verify:latest` Docker image exists on the VM
   (rebuild via `docker/build-verify-image.sh` if not); set `AGENT_DAILY_USD_CAP` (~$2-3/day)
   now that paid keys are live.
2. ~~**Remaining OpenCode parity**~~ — DONE (pt.2): user-authored `/commands` + real LSP shipped
   on `claude/commands-and-lsp`. `docs/OPENCODE_GAP.md` updated (all High-value gaps closed).
3. **Self-engineering dogfood test** (not yet run): seed an existing multi-file project in the
   workspace, ask the platform to "add feature X + a test, run it" and confirm the read→edit→
   run loop works on a live codebase (proves "point it at a repo, ask for a feature"). The new
   `diagnostics` tool makes this stronger — the agent can lint before running.
4. ~~**Finish the UI redesign**~~ — DONE (pt.2): chat-list grouping/titling, run-summary header,
   right-panel hierarchy shipped. Verify visually on a machine with data/keys (this session's
   clone had none). Further polish (mobile pass) still open.
5. **A/B validation on `evals/cases.yaml`** once comfortable — V4-Pro-plan vs GLM-plan, and the
   ported prompt overlays on/off, on real numbers (harness gained `setup.files` seeding).
6. *(carried)* off-site backups (`BACKUP_UPLOAD_CMD`), CI actions bump off Node-20, mobile pass.

**Decide re local-only work:** the news-agents (finance-news/tech-scout, `tools/feeds.py`,
`AGENTS.md`, `docs/NEWS_AGENTS_PLAN.md`, `docs/RELIABILITY_PLAN.md`) are uncommitted and won't
be on another laptop. Either commit them to a branch, `git stash` + carry the patch, or leave
them (they were deferred). Ask the owner before committing — they chose to keep these local.

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
  identity `Nikethan <nikethan160902@gmail.com>` (don't touch global git). **`gh` CLI is
  installed & authed** (accounts `Nikethan16` [active] + `Nikethan-cbc`; token scopes
  gist/read:org/repo/workflow — NO `delete_repo`). `git_push`/`create_pull_request` read
  `GITHUB_TOKEN` from env (derive one with `gh auth token`).
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
