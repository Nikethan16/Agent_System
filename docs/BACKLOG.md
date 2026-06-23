# BACKLOG — what's left to do

_Last updated: 2026-06-18. The prioritized list of remaining work. Nothing here is blocking —
the app is complete and deployed live. Items are roughly ordered by value. See `HANDOFF.md`
for current state and `STATUS.md` for what's already done._

---

## ✅ Orchestration issues — ADDRESSED on branch `claude/coding-engine-port` (2026-06-20)
All 7 issues below were fixed as part of the "absorb OpenCode's coding-engine design" work
(see `HANDOFF.md`). Each fix shipped as its own commit with tests. **#2 is a MITIGATION, not a
root fix** (see the scheduled phase-2 item at the bottom of this section).

1. ✅ Leaked raw tool-call markup as final → `_looks_like_raw_toolcall` + one-shot re-prompt
   in both loops (`core/agent.py`, `core/orchestrator.py`), false-positive guarded.
2. ✅ Research death-spiral → near-cap synthesis nudge + force `_finalize_from_board` at the
   cap, **AND the root fix now shipped**: within-run **compaction** (`_compact_messages` in
   `core/agent.py`, wired into both loops) summarizes old turns so long tasks stop reaching the
   cap. (The mitigation remains as a backstop.)
3. ✅ LEAD re-plans identical template → plan-repeat guard + plan-only-round counter.
4. ✅ Tier/agent cost mismatch + dispatcher fragility → `_effective_tier` (run at the cheaper
   of routed/agent tier) + `select_agent` tolerates a bare/embedded agent id.
5. ✅ research-report skill over-triggers → `use_skills=(tier>=2)` skips auto-matching on
   trivial tier-1 tasks (`core/skills.py` `auto=` flag).
6. ✅ Shared-workspace collisions → optional per-build sub-workspace behind
   `AGENT_TASK_SUBWORKSPACE` (OFF by default), `fresh_build_slug` in `core/tools.py`.
7. ✅ `run_bash`/`write_file` `/ws` path mismatch → `_safe` maps the Docker mount prefix.

**✅ PHASE 2 — SHIPPED (branch `claude/phase2-and-hardening`):** within-run **context
compaction** (`core/agent.py:_compact_messages`, both loops, triggers at 80% of the context
budget, preserves tool-sequence validity) + a **post-edit syntax verifier** (in-process
`.py`/`.json`/`.yaml` check appended to write/edit results — the safe, offline stand-in for
OpenCode's LSP; full LSP confirmed not worth it). Both tested.

---

## 🔎 Original observations (for reference — 2026-06-18)
Found by running `scripts/inspect_run.py` against a real multi-turn session and reading the
full event timeline + generated workspace files.

1. **Garbled/leaked special-token tool-call output shown as the final answer** — raw model
   tokens like `<｜DSML｜tool_calls>` and `<tool_call><function=run_bash>` (including a
   hallucinated nonexistent tool `run_shell`) were emitted directly as the user-facing `final`
   message, twice in one session, instead of being parsed/retried.
2. **Tier-3 research delegation death-spirals on the iteration cap** — both a subagent and the
   LEAD hit `MAX_MASTER_ROUNDS`/iteration cap (20) on a research task and returned the raw,
   unresolved subtask text as `final` instead of a synthesized answer or an explicit failure.
3. **LEAD re-plans the identical generic template repeatedly before acting** — observed 7
   re-plans (~320+s) on a tier-3 build task before any tool use, all producing the same plan.
4. **Tier/agent cost mismatch** — tier-1-classified tasks were executed by `general`/`research`
   specialists that are themselves configured at tier 2 (`config/agents.yaml`), undermining the
   cost-tier separation; the LLM-based specialist dispatcher (`core/agents.py:select_agent`)
   failed in this run and fell back to keyword matching.
5. **`research-report` skill over-triggers on trivial factual questions** — e.g. "capital of
   France" produced a full report-format answer in ~87s instead of a one-line fact.
6. **One shared workspace per chat session causes file collisions** — `session_workspace()`
   gives standalone chats one folder regardless of how many unrelated things get built in that
   chat; a Todo API + a URL shortener + benchmark project files ended up mixed in the same
   folder and confused later turns referencing "the project."
7. **`run_bash` / `write_file` path conventions disagree** — the Docker sandbox's in-container
   view (e.g. `/ws` owned by uid 1001) and the host-side `write_file` path expectations
   disagree, causing a hard "escapes workspace" block on a legitimate edit attempt.

Also unresolved (lower priority, separate from the above): session
`6dc676e500a541e9b966849004545c70` has **zero trace events** — not yet investigated whether it
never ran or traces failed to write.

---

## ✅ Recently shipped (2026-06-18) — public exposure via Tailscale Funnel + rate limiting
- **`scripts/inspect_run.py`** (PR #3) — read-only run diagnostics (timeline, span-tree,
  workspace files, last message). This is what surfaced the issues listed above.
- **`server/ratelimit.py`** (PR #4) — per-IP sliding-window request cap on every `/api/*` call
  + login brute-force lockout on `/api/login`, both fail-open on misconfig. Wired into
  `server/app.py` (middleware) and `server/api/auth_routes.py`.
- **Public HTTPS URL via Tailscale Funnel** — `https://agentcore.tail1d9a60.ts.net`, free, no
  domain purchased. VM hostname renamed to `agentcore` for a cleaner URL. The app is reachable
  from any device now, gated by the email+password login (+ the rate limiting above).

## ✅ Recently shipped (2026-06-15) — repo mode, Docker sandbox, tracing, ANN index
These four were built and pushed (branch `claude/serene-lamport-r1ix0k`, commit `513eb24`).
Code is done; the items below note the **operational steps** still needed to activate them live.

- **"Work on a repo" mode** — `tools/github.py` (git_clone/status/diff/log/checkout/commit/push +
  create_pull_request via GitHub REST), a `repo-engineer` agent (`config/agents.yaml`), and a
  `repo` playbook (clone→plan→branch→implement→verify→push→pr). PR/push are `requires_human`.
- **Docker shell sandbox (hardened)** — `core/tools.py`: host-shell fallback removed (fails closed),
  hardened `docker run` (cap-drop, no-new-privileges, read-only, tmpfs, pids/mem/cpu limits, timeout
  cleanup). `run_bash` drops to RISK_WRITE when `AGENT_BASH_DOCKER_IMAGE` is set (no human click).
- **Langfuse distributed tracing** — `server/trace.py` rewritten into a span tree (run → subagent →
  LLM generation with model/token-split/cost/latency). Offline JSONL still always-on. core stays
  offline via a callback hook + ContextVar in `core/llm.py`.
- **ANN vector index** — `server/vectorstore.py` (NumPy matrix, full-corpus, no `_MAX_SCAN` ceiling);
  `memory.recall` + `rag.retrieve` use it with graceful fallback to the Python loop / lexical.

**To activate live on the server (operational, not code):**
1. Build/pull an **ARM64** sandbox image; set `AGENT_BASH_DOCKER_IMAGE` and **unset
   `AGENT_DISABLE_BASH`** in the server `.env`. (docker-group setup per `docs/SETUP_GUIDE.md`.)
2. Add `GITHUB_TOKEN` to the server `.env` for clone/push/PR.
3. (Optional) add `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` (+ `LANGFUSE_HOST`) and
   `pip install langfuse` to send the span tree to the cloud.
4. Repo mode needs network in the sandbox for clone/installs → set `AGENT_BASH_DOCKER_NETWORK=bridge`.

---

## Post-build audit (2026-06-20) — findings & status
A full subsystem review (core loops, tools, server/data, model layer). **Implemented**
(branch `claude/phase2-and-hardening`): SQL aggregation for all spend analytics (were per-turn
full scans), missing migration indexes, scope-filtered fact/rule queries, O(catalog) context
budget, parallel-delegation exception isolation, resilient compaction (fallback chain),
near-cap-nudge priority, keystore data-loss guards (refuse-overwrite + atomic write + warnings),
`acquire()` never serving disabled keys, and grep/glob symlink containment.

**Deferred (tracked recommendations):**
- ✅ **Circuit breaker sensitivity — DONE** (`core/llm.py`, branch `claude/breaker-reliability`):
  trips only after `AGENT_BREAKER_THRESHOLD` (default 2) consecutive failures; never on
  `EmptyResponse`; breaker-skips recorded in metrics. Verified: tier-3 build churn dropped from
  ~15+ skips to 3. Also shipped: read-only-bash auto-allow (`core/policy.py`) + `list_files`
  hides `.skills` (`core/tools.py`). **Residual is free-tier model speed (~45s/call) — needs
  more NVIDIA keys / higher `AGENT_LLM_TIMEOUT`, not code.**
- **Abandoned hard-timeout futures** (`core/llm.py`): a stuck provider call keeps running on a
  worker after we stop waiting; under sustained provider stalls the 16-worker pool could
  saturate. Consider passing the timeout into the HTTP client and/or bounding the queue.
- **Streaming/image/embed key handling** (`core/llm.py`): these paths don't rotate/penalize keys
  on error, and `generate_image` ignores the encrypted key store (uses env only). Matters once
  image-gen is enabled.
- **`read_file` loads the whole file then slices** — fine for workspace-sized files; stream-and-
  stop only if very large files become common.
- **Spend rollup table** — only needed past ~1M Spend rows (years of 24/7 use); add
  `SpendDaily` + `spend.prune()` then.
- **`AGENT_SECRET_KEY` must be high-entropy** (no KDF stretching) — documented in PLACEHOLDERS.

## Features not built
- **Image generation** — code is ready; needs an `image_model:` in `config/models.yaml` + a
  matching provider key.
- **GitHub via MCP (alternative PR path)** — PR creation currently uses the GitHub REST API
  directly (self-contained, no MCP server needed). Wiring a GitHub MCP server into
  `config/mcp.yaml` is an optional alternative if richer GitHub operations are wanted.
- **More connectors** (Slack / DB via MCP) — the adapter (`tools/mcp.py`, `config/mcp.yaml`)
  exists; real servers aren't wired.
- **Browser / computer control** — intentionally skipped.
- **sqlite-vec / FAISS true ANN** — the NumPy index is fast to millions of rows; a real
  sub-linear ANN index is only worth it at much larger scale.

## UI / UX polish
- ✅ **Mobile pass (drawers)** — sidebar + artifacts panel no longer overflow narrow phones
  (verified 320/375px). Remaining: broader phone polish across all panels if desired.
- **Deep-polish the last two Settings panels** — Health and Schedules (Models/Memory/Fleet done).

## Performance / cost
- Add more **free NVIDIA keys** (`NVIDIA_NIM_API_KEY_1..N`) to multiply throughput.
- ✅ **Per-project budgets** — cumulative cap per project (`budget_usd`), enforced + tracked;
  `GET /api/projects/{id}/spend`. ✅ **Spend dashboard UI** — Settings → **Usage & cost** tab
  (today vs cap, all-time, 14-day bar chart, per-project table) via `GET /api/spend/overview`.
- Prompt caching — deferred (low payoff on NVIDIA's free tier; the classifier cache covers repeats).

## Reliability / quality
- Broaden integration tests further (more edge cases; multi-agent flow tests).

## Security / ops (the app is now public — see HANDOFF.md "Security follow-ups")
- ✅ **Encrypt stored API keys at rest** — `AGENT_SECRET_KEY` Fernet-encrypts `data/keys.json`
  (`core/keypool.py`), backward-compatible. ✅ **Off-site backups** already supported via
  `BACKUP_UPLOAD_CMD` in `scripts/backup.py` (operational: set the env var).
- Consider rotating/strengthening `AGENT_LOGIN_PASSWORD`; watch `journalctl -u agentcore` for
  repeated 401/429s on `/api/login` as a sign of scanning/brute-force attempts.
- Docker-group membership is root-equivalent — consider rootless Docker for the sandbox.

---

## Suggested next sequence
1. **Decide which orchestration issues to fix** (list above) — owner is reviewing real-run
   evidence before prioritizing.
2. **Activate repo mode + sandbox on the server** (`GITHUB_TOKEN`, flip `AGENT_DISABLE_BASH`
   off, set `AGENT_BASH_DOCKER_IMAGE`/`NETWORK`) and run `scripts/test_repo_mode.py`.
3. **Off-site backups** — set `BACKUP_UPLOAD_CMD` in server `.env`.
4. **Mobile pass** — CSS tweaks for phone drawers.
