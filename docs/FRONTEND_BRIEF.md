# Frontend Design Brief & Build Prompt — AGENT // CORE

Paste the **PROMPT** section below into v0.dev / Google Stitch (or any AI UI builder).
The **INTEGRATION CONTRACT** section is the exact backend API so the generated UI
actually works with our server. The **INTEGRATION NOTES** explain how to drop it in.

---

## PROMPT (copy everything in this block)

> Design and build a **clean, calm, modern web app** for a local AI agent platform
> called **AGENT // CORE** — think the polish of **Claude.ai** / **Anthropic Console**
> crossed with a coding-agent workspace (Claude Code / Cursor / Cowork). It is a
> **single-user local app**, desktop-first but responsive. Stack: **React + TypeScript
> + Tailwind CSS** (shadcn/ui welcome). No backend work — it talks to an existing API
> (documented at the end).
>
> ### Product in one line
> You chat with an AI that handles **both coding and general tasks**. For a complex
> goal, a **supervisor** splits the work across **specialist agents** (researcher,
> coder, frontend, doc writer, image, critic) that collaborate, use tools under a
> **security gate**, and produce **files/artifacts** you can preview. It picks the
> **cheapest capable model** automatically and shows live progress.
>
> ### Design direction (Claude-like — this is the most important part)
> - **Calm, minimal, editorial.** Lots of whitespace. A centered chat column
>   (~720–780px max width). Content-first, chrome-light.
> - **Default LIGHT theme** with a warm off-white background; include a **dark theme**.
>   - Light: background `#FAF9F5` / surfaces `#FFFFFF` / hairline borders `#E8E5DD` /
>     text `#1A1A18` / muted text `#6B6862`.
>   - Dark: background `#1F1E1D` / surfaces `#262624` / borders `#3A3833` / text `#ECEAE3`.
>   - **Accent: a warm clay/terracotta `#D97757`** (Claude-like), used sparingly for
>     primary actions, the active state, and the streaming caret. Avoid neon.
> - **Typography:** a humanist sans (Inter / Geist) for UI. Optionally a **serif**
>   (e.g. Tiempos/Lora/Source Serif) for the assistant's prose to feel editorial.
>   Comfortable line-height, ~16px base.
> - **Soft & rounded:** 10–16px radii, subtle shadows, thin borders, gentle hover.
> - **Motion:** subtle. Streaming text types in with a caret; messages fade/slide in
>   ~150ms; nothing bouncy.
> - **Markdown + code:** assistant messages render markdown with **code blocks that
>   have a language label and a copy button**, tables, lists, links.
>
> ### Layout (3 zones, both side panels collapsible)
> 1. **Left sidebar** — app wordmark "AGENT // CORE"; a prominent **New chat** button;
>    a scrollable **chat history** list (rename on double-click, delete on hover);
>    at the bottom, a small **Models** section (see "Model panel" below). Collapsible to icons.
> 2. **Center — the conversation** —
>    - Header strip: connection status dot, a tiny **running-cost** readout (`$0.0000`),
>      and a small **... menu** (export chat as markdown, settings).
>    - **Message thread:** user messages (right-aligned bubble or subtle block) and
>      assistant messages (left, editorial). Assistant messages stream token-by-token.
>    - **Agent Activity (signature feature):** while a complex task runs, show an
>      elegant **collapsible timeline** under the assistant message — a vertical
>      stepper/tree showing: *routed* (difficulty tier), *plan* (the subtasks, optionally
>      grouped for parallel), *assign* (which specialist agent + which model + why),
>      *thinking*, *tool calls* (name + args, monospace), *QA verdict* (pass/fail),
>      *memory recalled*, *manager review*. Each step has a small colored tag and the
>      agent's name. This should feel like a clean live trace, not a debug log.
>    - **Composer** (bottom): big rounded multiline input ("Describe a task…"),
>      Enter to send / Shift+Enter newline, a **Send** button that becomes **Stop**
>      while running. A compact, tucked-away **options row or popover** (NOT a cramped
>      bar) with: an **Approvals mode** segmented control (`auto` / `careful` / `trusted`),
>      and toggles **Plan first**, **QA review**, **Parallel**, **Stream**, plus
>      **Max $** and **Max loops** number inputs. Keep these visually quiet.
> 3. **Right panel — Artifacts & Checkpoints** (collapsible) —
>    - **Artifacts:** a file tree/list of files the agents produced. Clicking a file
>      opens a viewer with tabs **Source / Preview / Diff**: Preview renders markdown
>      and **live-previews HTML in a sandboxed iframe**; Diff shows a unified diff with
>      green additions / red deletions vs the last checkpoint. A **refresh** button.
>    - **Checkpoints (rewind):** a list of workspace snapshots (one per turn, labeled
>      with the message); each has a **Restore** action with a confirm.
>
> ### Modals / overlays
> - **Approval request:** when the agent wants a risky/destructive action (e.g. delete a
>   database), show a focused **modal**: the tool name, a **risk badge**
>   (safe/write/critical), the arguments (monospace), the policy reason, the
>   **security-manager agent's reason**, and **Approve** / **Deny** buttons. This is a
>   trust moment — make it clear and a little serious, not alarming.
> - **Model panel / Scout:** show the cost-first routing — for each tier (Fast,
>   Balanced, Frontier) display the **model actually being used** (it auto-picks the
>   cheapest available), with a dropdown to override. A **"Scout models"** button
>   researches cheap/free/open-source models and shows a list of proposals with
>   checkboxes to **add** them. Emphasize "cost-first / free when possible."
> - **Background tasks (queue):** a small panel/drawer listing enqueued jobs with
>   status (queued / running / done / error) — tasks that run unattended.
>
> ### Tone & microcopy
> Confident, quiet, human. Empty state: a calm hero ("What should we build?") with a
> few example prompts. Avoid jargon in the UI; keep technical detail inside the
> collapsible activity timeline.
>
> ### Deliverables
> A responsive React + TS + Tailwind app implementing: sidebar + sessions, chat thread
> with streaming + markdown/code, the agent-activity timeline, the composer with its
> options, the right-panel artifacts (source/preview/diff) + checkpoints, the approval
> modal, and the model/scout panel. Wire it to the API in the contract below using
> `fetch` for REST and a native `WebSocket` for the live run. Use **relative URLs**
> (same origin). Light + dark themes with a toggle.

---

## INTEGRATION CONTRACT (give this to the builder too — it must match exactly)

**Base:** same origin. REST under `/api`, live run over WebSocket. No auth (local).

### REST
- `GET /api/health` → `{ ok: true }`
- `GET /api/models` → `{ tiers, catalog, strategy, resolved }`
  - `tiers`: `{ tier1:{label,model,max_tokens}, tier2:{...}, tier3:{...} }`
  - `catalog`: `[{ id, provider, free?, cost?, tier_hint?, good_for?, requires_env? }]`
  - `strategy`: `"cheapest" | "fixed"` · `resolved`: `{ tier1:"<model id>", tier2, tier3 }`
- `POST /api/models/tier` `{ tier, model }` → ok
- `POST /api/models/scout` → `{ proposal: [catalog items], cost }`
- `POST /api/models/catalog` `{ models: [...] }` → `{ ok, catalog }`
- `DELETE /api/models/catalog/{id}` → `{ ok, catalog }`
- `GET /api/agents` → `[{ id, label, tier, capabilities, tools, when_to_use }]`
- `POST /api/sessions` `{ title }` → `{ id, title, created_at, updated_at }`
- `GET /api/sessions` → `[session]` (newest first)
- `GET /api/sessions/{id}` · `PATCH /api/sessions/{id}` `{ title }` · `DELETE /api/sessions/{id}`
- `GET /api/sessions/{id}/messages` → `[{ role:"user"|"assistant", content, cost, created_at }]`
- `GET /api/sessions/{id}/files` → `{ root, files:[{ path, size, ext }] }`
- `GET /api/sessions/{id}/file?path=…` → `{ path, ext, binary, content }`
- `GET /api/sessions/{id}/changes` → `{ changes:[{ path, status:"added"|"modified"|"deleted" }] }`
- `GET /api/sessions/{id}/file/diff?path=…` → `{ path, changed, diff }` (unified diff text)
- `GET /api/sessions/{id}/checkpoints` → `[{ id, label, created_at }]`
- `POST /api/sessions/{id}/restore` `{ checkpoint_id }` → `{ ok }`
- `POST /api/enqueue` `{ session_id, text, max_usd?, max_iterations? }` → `{ id }`
- `GET /api/jobs?session_id=…` → `[{ id, status, text, result, created_at }]` · `GET /api/jobs/{id}`

### WebSocket — live run
Connect: `new WebSocket(\`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/ws/${sessionId}\`)`

**Client → server**
- Start a run:
  `{ type:"run", text, max_usd, max_iterations, mode:"auto"|"careful"|"trusted",
     plan_first:boolean, review:boolean, parallel:boolean, stream:boolean }`
- Execute an approved plan: same `run` but add `subtasks:[string,...]` (from a `plan` event with `plan_only`).
- Answer an approval: `{ type:"approval_response", id, allowed:boolean, reason? }`
- Stop: `{ type:"stop" }`

**Server → client** (each is `{ type, ... }`, render in order):
- `route` `{ tier:1|2|3, task_type, reason, routed_model }` — difficulty routing
- `plan` `{ subtasks:[...], plan_only?:true, groups?:[[...]] }` — if `plan_only`, show "Run this plan"
- `assign` `{ agent, label, model, subtask?, reason, step? }` — a specialist starts
- `thought` `{ agent, text }` · `tool` `{ agent, name, args }`
- `token` `{ text }` — **append to the current assistant message** (final answer streaming)
- `agent_token` `{ agent, text }` — per-turn streaming (only when `stream:true`); show as a live line
- `manager_review` `{ tool, approved, reason }` · `critic` `{ passed, issues, summary }`
- `memory` `{ items:[...] }` — notes recalled from past chats
- `approval_request` `{ id, tool, args, risk, reason, manager_reason }` — **open the approval modal**
- `blocked` / `denied` `{ agent, name, reason }`
- `final` `{ text, cost }` — the finished answer (reconcile streamed text) · `limit` / `error` / `stopping`
- `run_complete` `{ cost }` — run finished; refresh files + checkpoints

**Turn flow:** save the user msg → open WS → send `run` → stream events into the
thread + activity timeline → on `approval_request` show modal and reply → on
`final`/`run_complete` finish and refresh the right panel.

---

## INTEGRATION NOTES (how we drop it into this repo)
1. The new app must build to static files. We serve them from `web/dist` (FastAPI
   already mounts that at `/`), so **keep relative `/api` + same-origin WebSocket URLs**.
2. Two ways to integrate:
   - **Replace `web/`** with the generated project (keep `vite.config.ts`'s dev proxy of
     `/api` → `http://localhost:8000` with `ws:true`), then `npm --prefix web run build`.
   - Or keep it separate and just `cp` its build output into `web/dist`.
3. Don't invent backend endpoints — everything the UI needs is in the contract above.
4. Send me the generated code and I'll wire it up, fix any contract mismatches, and
   make `run.ps1` serve it.

## Inspiration sources
- **Claude.ai** chat + **Anthropic Console** (console.anthropic.com) — the calm, warm, editorial feel.
- **Vercel v0** (v0.dev) and **shadcn/ui** (ui.shadcn.com) — clean component patterns.
- **Linear** (linear.app) — minimal, fast, tasteful.
- **Cursor** (cursor.com) & **Cline** — agent activity / diff / file panels.
- **Raycast** (raycast.com) — compact command surfaces & toggles done tastefully.
- **Perplexity** — sources/steps shown elegantly inline (good model for the activity timeline).
