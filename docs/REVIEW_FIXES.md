# Review Fixes — changelog

This documents the fixes applied in response to the full code review, grouped by
the review's severity. Each entry says **what was wrong**, **what changed**, and the
**files touched**. Verified by `python scripts/smoke_test.py` (27/27 pass), a clean
backend import, `tsc --noEmit` (now in **strict** mode), and `vite build`.

---

## CRITICAL

### 1. Live API key committed in `.env`
- **Was:** a real `NVIDIA_NIM_API_KEY` sat in `.env`, and there was no `.gitignore`.
- **Now:** key removed from `.env`; added a `.gitignore` that excludes `.env`,
  `data/`, `workspace/`, `audit.log`, `config/models.discovered.yaml`, venv, and
  `node_modules`. `.env.example` now warns never to commit a filled-in `.env`.
- **⚠️ Action still required by you:** the leaked key must be **rotated** at
  build.nvidia.com — removing it from the file does not un-leak it.
- **Files:** `.env`, `.gitignore` (new), `.env.example`

### 2. No authentication on any endpoint / WebSocket
- **Was:** every REST route and the WS were wide open — anyone reachable could run
  agents (shell), spend budget, and read/delete sessions.
- **Now:** new `server/auth.py` gate. If `AGENT_AUTH_TOKEN` is set, **every** API
  request and WS connection must present it (`Authorization: Bearer`, `X-Auth-Token`,
  or `?token=` for the WS). If it's unset, the API answers **loopback only** and
  refuses other hosts — so it can't be deployed open by accident. Wired as a
  router-level `Depends` on all routers; the WS authorizes before `accept()`. The
  SPA shell at `/` stays public; the API behind it is gated. Frontend attaches the
  token from a Settings field (stored in `localStorage`).
- **Files:** `server/auth.py` (new), `server/app.py`, `server/api/ws.py`,
  `web/src/lib/api.ts`, `web/src/components/SettingsModal.tsx`

### 3. Arbitrary code execution with no real sandbox
- **Was:** `run_bash` ran `shell=True` confined only by cwd (absolute paths escape);
  in default `auto` mode it escalated only to the LLM manager, not a human; `trusted`
  auto-approved it.
- **Now:** `run_bash` is registered with `requires_human=True`, so the deterministic
  gate forces a human approval for it in `auto`/`careful` mode. Added an
  `AGENT_DISABLE_BASH` kill-switch (the Docker image sets it `=1` by default) so
  deployments run shell only inside a real container/VM. Added a clean timeout error.
- **Files:** `core/toolbelt.py`, `core/tools.py`, `Dockerfile`, `.env.example`

---

## HIGH

### 4. Client-controlled, unbounded budgets
- **Was:** `max_usd`/`max_iterations` came from the client with no ceiling.
- **Now:** clamped server-side to `AGENT_MAX_USD_CEILING` (default 5.0) and
  `AGENT_MAX_ITER_CEILING` (default 60) on both the WS run path and the job queue;
  the job API also rejects absurd values (`Field(le=…)`).
- **Files:** `server/api/ws.py`, `server/jobs.py`, `server/api/jobs.py`

### 5. SSRF in `web_fetch` / `web_search`
- **Was:** only the `http(s)://` scheme was checked; could hit `169.254.169.254`
  (cloud metadata), `localhost`, and private IPs, and followed redirects to them.
- **Now:** `_guard_url` resolves the host and rejects loopback/private/link-local/
  reserved/multicast addresses (checks **every** resolved IP), and a custom redirect
  handler re-validates each hop. `web_search` guards its provider URL too.
- **Files:** `tools/web.py`

### 6. Path traversal via unvalidated IDs (incl. a destructive `rmtree`)
- **Was:** `session_id`/`checkpoint_id`/`project_id` from REST params were joined
  straight onto filesystem paths; `restore_checkpoint` `rmtree`s the joined path.
- **Now:** `db.safe_id()` validates IDs as 32-char UUID hex before any join
  (`session_workspace`, `_cp_dir`, `projects._dir`, `jobs.enqueue`). A global
  `InvalidId → 400` handler returns a clean error instead of a 500.
- **Files:** `server/db.py`, `server/projects.py`, `server/jobs.py`, `server/app.py`

### 7. Stored XSS via unsanitized SVG artifacts
- **Was:** `Svg` injected raw `.svg` file contents with `dangerouslySetInnerHTML` —
  agent-produced SVG can carry `<script>` and runs in the app origin.
- **Now:** SVG renders inside a sandboxed `<iframe sandbox="">` (no `allow-scripts`),
  so embedded scripts can't execute and have no access to the app origin.
- **Files:** `web/src/components/Mermaid.tsx`

### 8. WebSocket mutated the wrong session / left runs stuck; no REST error handling
- **Was:** switching chats mid-run left the socket open, applying events to the new
  session; a dropped socket left the bubble stuck "pending"; `fetch` calls had no
  `.ok`/`.catch`, so one failure threw an unhandled rejection.
- **Now:** the socket is tagged with its session and torn down on session switch
  (`running` reset); stale-session events are ignored; a socket that closes before
  `run_complete` clears the pending bubble with an "interrupted" note. `api.ts` is a
  single wrapper that checks `response.ok` and throws a descriptive `ApiError`; store
  load actions catch and surface errors as a local note instead of crashing.
- **Files:** `web/src/lib/store.ts`, `web/src/lib/api.ts`

### 9. Job queue didn't recover after a restart
- **Was:** jobs left `running` when the process died stayed stuck forever.
- **Now:** `start_worker()` re-queues stale `running` jobs on boot (called from app
  startup), so in-flight work resumes.
- **Files:** `server/jobs.py`

---

## MEDIUM

### 10. MCP tools defaulted to fail-open
- **Was:** configured MCP tools defaulted to `risk=write`, `requires_human=False`.
- **Now:** default to `critical` + `requires_human=True` (loosen explicitly per
  server in `config/mcp.yaml` once trusted); the generic `mcp_call` is also critical.
- **Files:** `tools/mcp.py`

### 11. Catalog write had no validation
- **Was:** `update_catalog` persisted arbitrary client/LLM dicts (incl. unknown keys)
  to `models.discovered.yaml`.
- **Now:** `_clean_entry` whitelists + coerces fields (`id`, `provider`,
  `requires_env`, `free`, `cost`, `tier_hint` clamped 1–3, `good_for`) and drops junk.
- **Files:** `core/registry.py`

### 12. Input validation & status-code consistency
- **Now:** `EnqueueIn`/`TruncateIn`/`FeedbackIn` have `Field` bounds and a `Literal`
  for feedback; `delete`/`feedback`/`truncate` now 404 on a missing session; query
  params typed `Optional[str]`.
- **Files:** `server/api/jobs.py`, `server/api/sessions.py`

### 13. Trace cache leak + data race
- **Now:** the Langfuse per-session trace cache is bounded (512, oldest evicted) and
  mutated under the lock.
- **Files:** `server/trace.py`

### 14. Theme state duplicated/desyncing; message keys by index
- **Now:** theme lives in the store (persisted to `localStorage`, applied on load),
  consumed by Sidebar + Settings; message list keys on a stable per-message id, so
  edit/branch no longer attaches stale component state.
- **Files:** `web/src/lib/store.ts`, `web/src/components/Sidebar.tsx`,
  `web/src/components/SettingsModal.tsx`, `web/src/components/Chat.tsx`

### 15. Accessibility
- **Now:** approval + settings modals have `role="dialog"`, `aria-modal`, and
  Escape-to-close; session rows + star/delete are keyboard-operable
  (`role`/`tabIndex`/Enter/Space); composer icon buttons and number inputs have
  `aria-label`s.
- **Files:** `web/src/components/Chat.tsx`, `SettingsModal.tsx`, `Sidebar.tsx`,
  `Composer.tsx`

### 16. `memory.recall` full-table scan; unbounded checkpoints
- **Now:** `recall` scans only the most-recent `MEMORY_MAX_SCAN` (default 2000) rows;
  `create_checkpoint` prunes to the most recent `MAX_CHECKPOINTS` (default 20).
- **Files:** `server/memory.py`, `server/db.py`

---

## LOW

### 17. Number inputs couldn't be set to 0
- **Now:** parse guards on NaN instead of `|| default`, so `0` is accepted.
- **Files:** `web/src/components/SettingsModal.tsx`, `Composer.tsx`

### 18. Vite dev-proxy comment / port mismatch + bundle size
- **Now:** comment corrected to `:8800` (the real port), target overridable via
  `BACKEND_URL`; `manualChunks` splits react/markdown/highlight so the main bundle
  dropped ~531 kB → ~70 kB.
- **Files:** `web/vite.config.ts`

### 19. TypeScript not strict
- **Now:** `"strict": true` — typechecks clean.
- **Files:** `web/tsconfig.json`

### 20. Silent `except: pass`
- **Now:** project-file and discovered-catalog read failures are logged.
- **Files:** `server/projects.py`, `core/registry.py`

### 21. Dependency drift / Docker gaps
- **Now:** Python deps have upper bounds (`litellm>=1.55,<2`, etc.); Dockerfile copies
  `skills/`, runs as a non-root user, and disables bash by default.
- **Files:** `requirements.txt`, `Dockerfile`

---

## Deliberately NOT changed (and why)

- **Automatic WS reconnect mid-run:** the run is a server-side thread bound to one
  socket; a reconnected socket can't re-attach to it. Instead the client now fails
  gracefully (clears the stuck bubble, tells the user it was interrupted). A true
  resumable run needs the persistent task queue, which already exists for unattended
  work via `/api/enqueue`.
- **Real shell sandbox (container-per-run):** out of scope for a code edit; mitigated
  with `requires_human` + `AGENT_DISABLE_BASH`. Containerizing `run_bash` is the
  recommended next step before enabling shell in a deployment.
- **A few LOW cosmetic items** (dead `activity-pulse` CSS, duplicated copy/download
  helpers, `alert/confirm` → toast, keyboard nav on file cards/checkpoint rows) were
  left to keep this change focused on correctness/security; they're noted here.
- **Full unit-test suite:** the offline `scripts/smoke_test.py` was extended (auth
  gate) and still passes 27/27; broader unit coverage remains a follow-up.
