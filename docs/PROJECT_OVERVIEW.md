# AGENT // CORE — The Complete Project Reference

_This is the single, self-contained reference for the whole project. It is written so
that **anyone** — you, a new teammate, or a fresh AI chat with no prior context — can read
it top to bottom and understand **what the app is, how it's architected, and exactly how
every feature is implemented** (with the real files and mechanisms). If this is the only
file you read, you will still understand the system._

_Last updated: 2026-06-03 · Runs locally at http://localhost:8800 · see "LATEST ADDITIONS" at the bottom_

> Shorter companions: `CLAUDE.md` (rules, auto-loaded every chat), `STATUS.md` (checkbox
> tracker + changelog), `docs/PLACEHOLDERS.md` (keys you provide), `docs/COMPETITIVE.md`
> (peer-tool comparison), `README.md` (quick start). When those disagree with reality, this
> file is the intended source of truth for *how it works*.

---

## TABLE OF CONTENTS
1. What this app is (and the one unbreakable rule)
2. How to run it + the ports
3. Repository map — every important file in one line
4. The architecture & the life of one chat message
5. The engine (`core/`) — file by file, how each works
6. The platform — the three registries
7. The orchestrator: routing + the Claude-Code master loop
8. The dispatcher: how an agent is chosen
9. The security model — every layer, how it's coded
10. Agent Skills — how expertise is pulled in
11. The web application — backend + frontend
12. Cost-first models + the model-scout
13. Memory, tracing, the job queue, MCP, images, evals
14. The event contract (every event type)
15. The config files (what you edit)
16. What you must provide (placeholders)
17. How we compare to OpenClaw
18. The invariants + lessons learned
19. How to verify nothing is broken
20. What's done / what's left

---

## 1. What this app is (and the one unbreakable rule)

A **local, private, Claude-Code-style work assistant**. You chat with it in a browser; it
plans, writes and runs code, builds documents (Word/Excel/PowerPoint/PDF), researches, and
shows every step live. It saves your chats and the files it makes, asks permission before
risky actions, and by default runs on **free models** so it can cost $0.

**The one design idea behind everything:** anything that might change lives in a **config
file**, not in code. Models, agents, tools, skills, and security rules are all declarative.
That's why "add a capability" is usually a YAML edit, not a code change.

**The one rule we never break:** every AI model call goes through a single function
(`core/llm.py: complete`) and every run carries a **Budget** with a hard dollar cap and a
hard step cap. Nothing can loop forever or spend without a ceiling.

---

## 2. How to run it + the ports

```bash
# one-time setup (Windows; the project uses a .venv)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # add the provider keys you have (see §16)

# build the frontend once; the backend then serves it
npm --prefix web install
npm --prefix web run build
uvicorn server.app:app --port 8800        # open http://localhost:8800

# live frontend dev (hot reload), with uvicorn also running:
npm --prefix web run dev        # http://localhost:5173 (proxies API+WS to 8800)
```

**Ports:** **8800** is the one real port (the app: API + WebSocket + served UI). 5173 is
only the optional hot-reload dev server. We moved off 8000 permanently (a leftover
Docker/WSL process held it) and took Docker out of the daily flow.

**Important:** the project's Python lives in **`.venv`**, not the system Python. Run things
as `.venv\Scripts\python.exe ...` (or activate the venv) — the document-skill libraries and
all deps are installed there, not in system Python.

**Verify with no keys/cost:**
```
.venv\Scripts\python.exe scripts/smoke_test.py     # 26 offline checks (fake model)
.venv\Scripts\python.exe -m evals --dry-run        # validate the eval harness offline
```

---

## 3. Repository map — every important file in one line

```
config/
  models.yaml          tiers + the model CATALOG (the swap point); cost-first settings
  models.discovered.yaml   models the model-scout added (kept separate from the curated file)
  agents.yaml          the AGENT REGISTRY — each specialist as a YAML block
  policy.yaml          security rules: hard_block patterns + require_human patterns
  mcp.yaml             external MCP servers to connect (optional)
core/                  THE ENGINE — provider-agnostic, offline, stable
  llm.py               the ONE model call point + Budget (cost/step caps) + streaming/image/embed
  registry.py          loads models.yaml; resolves tier→model; cost-first selection
  router.py            cheap classifier: task → {tier, task_type, requires_web}
  tools.py             sandboxed file/shell tools + per-session workspace (contextvar)
  toolbelt.py          the TOOL REGISTRY — schema + risk label per tool
  agent.py             the generic agent loop (think→act→observe) + the approve() gate hook
  policy.py            deterministic security gate (Layer 2) + append-only audit log
  agents.py            the agent registry loader + the dispatcher (select_agent)
  orchestrator.py      the SUPERVISOR: router + the Claude-Code master loop + QA review
  blackboard.py        shared per-run scratchpad agents collaborate through
  skills.py            Agent Skills: load/select/inject/stage SKILL.md expertise
skills/                the skills themselves (each a folder with SKILL.md)
  python-project, web-frontend, research-report   (bundled, custom)
  docx, xlsx, pptx, pdf                            (real Anthropic document skills)
tools/                 OPTIONAL network capabilities (kept OUTSIDE core so core stays offline)
  web.py               web_search / web_fetch (+ wraps fetched pages as untrusted DATA)
  image.py             generate_image tool (needs an image model + key)
  mcp.py               real MCP stdio JSON-RPC client; registers MCP tools into the toolbelt
  mcp_example_server.py  a tiny bundled MCP server for testing
server/                THE WEB BACKEND (FastAPI)
  app.py               mounts the API routers + serves web/dist
  db.py                SQLite (SQLModel): sessions/messages/events/checkpoints + workspaces
  chat.py              ConversationManager: one turn → context + supervisor + persistence
  approvals.py         security Layers 3-4: security-manager agent + human approval bridge
  memory.py            cross-session memory (embedding or lexical recall)
  trace.py             per-run JSONL traces (+ optional Langfuse)
  jobs.py              persistent SQLite task queue + worker
  projects.py          Projects: shared instructions + knowledge files
  api/
    sessions.py        REST: create/list/get/rename/delete/star/feedback/truncate
    messages.py        REST: a session's message history
    workspace.py       REST: file tree, read a file, upload, diff vs checkpoint, versions
    models.py          REST: model tiers (get/swap), catalog, model-scout, /api/skills, /api/agents
    projects.py        REST: Projects CRUD
    jobs.py            REST: enqueue + job status
    ws.py              WebSocket: run a turn, stream events, approvals, stop
web/                   THE FRONTEND (React + TypeScript + Vite + Tailwind)
  src/App.tsx          shell: layout, Ctrl/⌘+K, settings, theme
  src/components/      Chat, Composer, Sidebar, RightPanel, FilesPanel, CheckpointsPanel,
                       SkillsPanel, ModelRail, JobsPanel, ProjectModal, SettingsModal,
                       CodeBlock, Mermaid
  src/lib/store.ts     Zustand state (sessions, live run, toggles)
  src/lib/api.ts       REST client + the run WebSocket hook
evals/                 the eval harness: cases.yaml + graders + runner (python -m evals)
scripts/
  smoke_test.py        26 offline regression checks with a fake model
  import_skill.py      copy a skill folder (e.g. from anthropics/skills) into skills/
docs/                  this file + CAPABILITIES/PLACEHOLDERS/COMPETITIVE/MODEL_REQUIREMENTS/UI_STRUCTURE_PLAN
data/                  runtime: app.db, workspaces/<session>, checkpoints/, traces/
audit.log              append-only log of every tool call + every gate decision
```

---

## 4. The architecture & the life of one chat message

```
 BROWSER (React, :8800)
   Chat thread · live Agent-Activity timeline · Files/Artifacts · Approve/Deny · Stop
        │ REST: create/list/load (sessions, messages, files)
        │ WebSocket /api/ws/<session>: stream events OUT, send approvals/stop IN
        ▼
 SERVER (FastAPI, server/)
   ws.py ── runs the turn in a worker THREAD; bridges events to the socket via a queue
   chat.py ── builds context (history + memory + project + attachments), sets the
              per-session workspace, calls the engine, persists messages+events+cost
   approvals.py ── when the engine escalates a risky tool: security-manager agent, then
                   (if needed) a human Approve/Deny card; blocks the worker until answered
   db.py ── SQLite saves everything; snapshots the workspace before each turn (checkpoint)
        ▼
 ENGINE (core/) — provider-agnostic, offline
   orchestrator.handle_task(...)
     router.classify → tier (1/2/3) + task_type
     tier 1-2 → ONE specialist agent (agent.run_agent loop)
     tier 3   → the LEAD master loop (todo list + delegate to specialists)
     every model call → llm.complete(...) under the run Budget (cost + step caps)
        ▼
 MODEL PROVIDER (chosen by config/models.yaml: NVIDIA free, Gemini, OpenRouter, Ollama…)
   reached only through LiteLLM, which normalizes 100+ providers to one format
```

**Step by step, what happens when you hit send (`server/chat.py: run_turn`):**
1. **Checkpoint** — the session's workspace is snapshotted so you can rewind to *before*
   this turn (`db.create_checkpoint`).
2. **Save** your message; **build context** = last 6 turns + recalled notes from past chats
   (memory) + project instructions/files + any attachment text (PDFs are text-extracted).
3. **Enter the session's isolated workspace** (`using_workspace(...)`, a contextvar) so all
   file/shell tools are sandboxed to `data/workspaces/<session>/`.
4. **Run the engine** (`handle_task`): classify → route → either one specialist or the LEAD
   master loop. Every step `emit`s an event that is (a) streamed to your browser live and
   (b) saved to SQLite and the trace file.
5. **Risky tool?** The engine calls the `approve()` hook → manager agent → maybe you → the
   tool runs or is denied; either way it's written to `audit.log`.
6. **Save** the final answer + the run's cost; **remember** the outcome for future recall.

---

## 5. The engine (`core/`) — file by file, how each works

The engine is the stable heart. It never imports a provider SDK, never makes a web call,
never contains a model name or any UI concern. Everything below is offline + deterministic
except the actual model calls (which all funnel through `llm.complete`).

### 5.1 `llm.py` — the single call point + the Budget
- **`complete(model, messages, tools=…, budget=…)`** is the *only* place `litellm` is
  called for text. It returns `(response, cost)` in OpenAI format regardless of provider.
  `litellm.drop_params=True` (so the same call works on any provider) and
  `litellm.num_retries=3` (free tiers rate-limit; transient 429s retry with backoff).
- **`Budget`** (a dataclass) holds `max_usd`, `max_iterations`, `spent_usd`, `iterations`,
  guarded by a `threading.Lock` (parallel subtasks share one budget safely). `check()`
  raises `BudgetExceeded` when either cap is hit; `add_cost()`/`tick()` accumulate. Every
  `complete()` call does `budget.check()` *before* and `add_cost()`+`tick()` *after* — so
  the caps are enforced centrally and can't be bypassed.
- **`Budget.child()` → `_SubBudget`** gives each agent its own local cap that ALSO forwards
  every spend/tick to the parent run budget — so a single agent can be capped without ever
  letting the global cap be exceeded.
- Also here (same pattern, same single-call-point + budget): **`generate_image`** (images),
  **`stream_complete`** (token-streamed text answers), **`embed`** (embeddings for memory),
  and **`stream_complete_tools`** (streaming *with* tool-calling, used for per-turn
  streaming — it reassembles tool calls from streamed deltas).

### 5.2 `registry.py` — model resolution + cost-first selection
- Loads `config/models.yaml`; `model_for_tier(tier, task_type)` is what the rest of the code
  asks instead of naming a model.
- Two strategies (`defaults.model_strategy`): **`fixed`** uses each tier's `model:` line;
  **`cheapest`** (the default) calls **`cheapest_for(level, task_type)`**, which:
  1. takes the **catalog** (models.yaml `catalog:` + any model-scout discoveries),
  2. keeps only models that are **available** (`requires_env` key is set in the environment)
     AND **capable enough** (`tier_hint >= needed level`),
  3. if a `task_type` is given, prefers models whose `good_for` lists it,
  4. sorts by **(free first, then lowest `cost`)** and returns the cheapest.
  → Add a free provider's key and free models start getting used automatically. No code
  change, no hardcoded names.
- `set_tier_model()` allows the UI to live-swap a tier's model; `update_catalog()` /
  `remove_from_catalog()` persist the model-scout's discoveries to
  `config/models.discovered.yaml` (the curated `models.yaml` stays pristine).

### 5.3 `router.py` — the cheap classifier
- `classify(task)` makes one **tier1 (cheapest) model** call with a strict
  JSON-only system prompt and returns `{tier:1|2|3, task_type, requires_web, reason,
  routed_model}`. It tolerates stray text (slices to the `{...}`) and, on any failure,
  **falls back to a safe tier** instead of crashing. Note: the category is returned as
  **`task_type`**, never a bare `type`, so spreading it into an event can't clobber the
  event's own `type` field.

### 5.4 `tools.py` — the sandbox (the agent's hands)
- Four functions: `read_file`, `write_file`, `list_files`, `run_bash`. Every path goes
  through **`_safe(path)`**, which resolves it and refuses anything that escapes the current
  workspace root → tools are sandboxed.
- The sandbox root is a **contextvar** (`using_workspace(root)` is a context manager). The
  default is `./workspace`; the server sets it per session to
  `data/workspaces/<session_id>` so each chat's files are isolated. The containment check is
  unchanged — only the *location* is per-session. `run_bash` runs with a 30s timeout in that
  workspace.

### 5.5 `toolbelt.py` — the tool registry (3rd registry)
- A **`Tool`** = OpenAI schema + the callable + a **risk** label
  (`safe`/`write`/`critical`) + a `requires_human` flag. `register_fn(...)` adds one.
- The four built-in file/shell tools are registered here with risks: read/list = `safe`,
  write = `write`, **run_bash = `critical`**. Network tools (web/image/MCP) register
  themselves from the `tools/` package when imported — **core never imports `tools/`**, so
  importing the engine alone pulls in no web/provider code.
- `schemas_for(names)` builds the tool-schema list for whatever subset an agent is allowed.

### 5.6 `agent.py` — the generic think→act→observe loop
- **`run_agent(task, system, model, …, allowed_tools, approve, stream)`** is the loop every
  specialist runs. It:
  1. resolves the agent's **allowed** tool schemas (least privilege),
  2. calls the model (`complete` or, if `stream`, `stream_complete_tools`),
  3. emits a `thought` for any content, and for each tool call emits a `tool` event and runs
     it through the gate,
  4. feeds tool results back and repeats.
- **Loop guard** `MAX_TOOL_ROUNDS = 8`: after 8 tool rounds it drops tools and nudges the
  model to give a final answer — so a weak model can't spin on tools forever.
- **Graceful errors**: `BudgetExceeded` → a clean "(stopped: …)"; any provider error (e.g. a
  surviving rate-limit) → a friendly message instead of a crash.
- **`_run_one_tool`** is the security choke point (see §9): it calls `policy.evaluate`,
  handles `block`/`escalate`/`allow`, calls the `approve` callback on escalation, **audits
  every decision**, then runs the tool.

### 5.7 `blackboard.py` — how agents share results
- A thread-safe per-run list of `(agent, key, content)` entries. Agents don't message each
  other directly (that loops and burns budget); instead each `post()`s its result and
  downstream agents read a bounded `digest()`. The LEAD passes this digest as context when
  it delegates, so a later specialist can see earlier results.

---

## 6. The platform — the three registries

Everything extensible hangs off three declarative registries (same philosophy as models):

| Registry | File(s) | Add one by… | Used by |
|---|---|---|---|
| **Models** | `config/models.yaml` + `core/registry.py` | adding a catalog entry | `model_for_tier` everywhere |
| **Agents** | `config/agents.yaml` + `core/agents.py` | adding a YAML block | the dispatcher + master loop |
| **Tools** | `core/toolbelt.py` (+ `tools/`) | `register_fn(...)` | the agent loop + the gate |

**The agent roster** (from `config/agents.yaml`): each agent declares a **tier**, a **tool
allowlist** (least privilege), **capabilities**, a **when_to_use** (the dispatcher reads
it), and a **prompt**:

| Agent | Tier | Allowed tools | Purpose |
|---|---|---|---|
| supervisor | tier3 | none | (legacy planner prompt; the master loop is the live path) |
| general | tier2 | **none** | chat / explanation / writing — tool-less so it can never loop |
| coder | tier2 | read/write/list/**run_bash** | write, run, debug code |
| frontend | tier2 | read/write/list/run_bash | build previewable web UI |
| research | tier2 | web_search/web_fetch/write | cited web research (treats pages as DATA) |
| doc | tier2 | read/write/list | polished documents/reports |
| image | tier2 | generate_image/write | images (needs an image model + key) |
| critic | tier2 | read/list/run_bash | QA — concrete pass/fail JSON only |
| model-scout | tier2 | web + read/write | (internal) research cheap/free models |
| security-manager | tier2 | none | (internal) approve/deny risky actions |

`agents.catalog()` hides the three internal agents (supervisor, security-manager,
model-scout) from the dispatcher menu.

---

## 7. The orchestrator: routing + the Claude-Code master loop

`core/orchestrator.py: handle_task(task, budget, emit, approve, plan_only, subtasks,
review, parallel, stream)` is the entry point.

**Routing:**
- It calls `classify(task)` → emits a **`route`** event → reads `tier` + `task_type`.
- **Tier 1–2** → **one specialist**: `select_agent` picks it, emits **`assign`**, then
  `_do_subtask` runs it (with optional QA, below). This single agent runs its own
  think→act→observe loop — that alone is "Claude-like" for simple work.
- **Tier 3** → the **LEAD master loop** (`_master_loop`).

**The master loop (`_master_loop`) — modeled on Claude Code's single-threaded master loop:**
1. Picks a **reasoning-tier model** for the lead.
2. Builds the lead's system prompt from the live **agent menu** + the live **skills menu**.
3. **Seeds an explicit plan**: `_make_plan` asks a tier3 model for 1–5 ordered steps; emits
   a **`plan`** event carrying the **todo list**. (Seeding guarantees a visible breakdown
   even if the model wouldn't spontaneously plan.)
4. Loops (cap `MAX_MASTER_ROUNDS = 16`), giving the lead these meta-tools:
   - **`write_todos`** — create/update the plan; re-emits the `plan` event.
   - **`delegate(agent, instruction, skill?)`** — hand a scoped step to a specialist. The
     specialist runs with its own tools + the blackboard digest as context, and can pull a
     named **skill**. Subagents **cannot delegate again** (depth-limited;
     `MAX_DELEGATIONS = 10`). Each delegation emits an **`assign`** event and posts the
     result to the blackboard.
   - the four file/shell tools, for small steps the lead does itself.
5. **Reminder injection**: after each round the current todo list is re-appended to the
   messages, so the model never loses the plan (the key trick that keeps it on track).
6. When the lead replies with **no tool call**, that text is the final answer. If it runs
   out of budget mid-flight, `_finalize_from_board` synthesizes an answer from the
   blackboard so you still get something.

**QA review (the critic) — `review` is tri-state:** `True` (always), `False` (never),
`"auto"` (default). `_auto_review` turns it on for tier3, and for tier2 coding/writing/
data/math; it skips trivial/look-up tasks to save cost. When on, `_review` runs the
**critic** agent, which returns strict pass/fail JSON; on fail, the work is sent back to the
same agent **once** with the issues as feedback. Emits a **`critic`** event.

**Plan-first mode** (`plan_only=True`): produce the plan, emit it, and stop — the UI shows
it and the user approves; approval re-enters `handle_task` with `subtasks=[…]`, which seeds
the master loop with those exact steps.

---

## 8. The dispatcher: how an agent is chosen

`core/agents.py: select_agent(task)`:
- Builds a **menu** from `agents.catalog()` (id + when_to_use) and asks the cheap
  **dispatcher-tier** model to pick one agent as JSON `{"agent","reason"}`.
- **Critical bug-fix baked in:** the prompt contains a literal JSON example with braces, so
  it uses `str.replace("{menu}", …)` **not** `str.format()` (which would choke on
  `{"agent"}` and silently fall back every time — that was the real cause of an earlier
  "explain isn't working; it routes to the coder" bug).
- **Fallback** `_fallback_select`: if the model returns junk, keyword matching decides — and
  explanation/question phrasings ("explain", "what is", "how does"…) without make-verbs go
  to the tool-less **general** agent, *even if* the word "code" appears. So "explain this
  code" is a chat answer, not a coder run.

---

## 9. The security model — every layer, how it's coded

Defense in depth. An action escalates through gates; the riskier it is, the more sign-off it
needs. Everything hangs off the single `approve(tool, args, decision)` hook in the agent
loop, so the loop itself stays simple.

```
agent wants tool(args)         [core/agent.py: _run_one_tool]
 0. Least privilege  — allowed_tools list per agent (config/agents.yaml). Not listed → unavailable.
 1. Risk label       — toolbelt: safe / write / critical (+ requires_human)
 2. Policy gate      — core/policy.py + config/policy.yaml (deterministic, no model):
                         · hard_block pattern → BLOCK (e.g. rm -rf /, fork bombs)
                         · require_human pattern OR critical tool → ESCALATE
                         · else → ALLOW
 3. Manager agent    — server/approvals.py: the security-manager agent reviews the action
                         in context → approve/deny + reason (fails CLOSED on error)
 4. Human            — Approve/Deny card over the WebSocket; the worker thread BLOCKS on a
                         threading.Event until you answer (or 300s timeout → deny)
 → every decision (allow/deny/block) is appended to audit.log with agent/tool/args/reason
```

- **`core/policy.py: evaluate(tool, args)`** serializes the args to a lowercase blob and
  tests the compiled `hard_block` / `require_human` regexes from `config/policy.yaml`.
  Returns a `Decision(action, reason, requires_human)`. `audit(record)` appends one JSON
  line per decision under a lock.
- **`server/approvals.py: ApprovalBroker`** implements Layers 3–4 and the **permission
  modes** (set per run in the UI / `/mode`):
  - **`trusted`** — auto-approve everything except hard-blocks (no manager/human).
  - **`auto`** (default) — manager agent always; human only for `requires_human` actions.
  - **`careful`** — manager agent + human for **every** escalated action.
  The manager runs in the worker thread; the human prompt bridges to the async socket via a
  `threading.Event` that the WebSocket `resolve()`s when you click. **Irreversible actions
  require BOTH the manager and your click.**
- **Checkpoints / rewind** (`server/db.py`): the workspace is `copytree`-snapshotted
  **before every turn** into `data/checkpoints/<session>/<id>`. `restore_checkpoint` wipes
  the live workspace and copies a snapshot back. The UI / `POST /api/sessions/{id}/restore`
  drive it. The diff view compares the live file to the latest checkpoint.

This layered, auditable, human-in-the-loop design is the single biggest way this app differs
from "just let the agent do it" assistants.

---

## 10. Agent Skills — how expertise is pulled in (`core/skills.py`)

A **skill** is a folder `skills/<name>/` with a **`SKILL.md`**: YAML frontmatter (`name`,
`description`, optional `keywords`/`agents`) + a markdown body of expert instructions, plus
optional `scripts/` and reference files. This is exactly Claude's format, so any skill from
`github.com/anthropics/skills` drops in unchanged.

**Progressive disclosure, in four steps:**
1. **Load** (`load()`): scan every `skills/*/SKILL.md`, parse frontmatter+body.
2. **Select** (`select(task, agent, names=…)`): cheap + deterministic (no model call).
   Scores each skill by overlap between the task words (minus stopwords) and the skill's
   name+keywords+description, and **doubles** the score for distinctive trigger words
   (`_SIGNALS`: e.g. "spreadsheet/excel"→xlsx, "deck/slides"→pptx, "word/letter"→docx,
   "pdf"→pdf). `names=` lets the LEAD **explicitly** force a skill it chose via
   `delegate(skill=…)`; the rest auto-fill. Returns the top ~2.
3. **Inject** (`context(skills)`): the selected skills' full bodies are added to the agent's
   prompt — so it works from an expert checklist, not a blank slate. Emits a **`skill`**
   event (the purple chip in the UI).
4. **Stage** (`stage(skills)`): copies the skill's `scripts/references/assets` **and** its
   loose top-level reference files (e.g. `pdf/REFERENCE.md`, `pdf/FORMS.md`,
   `pptx/EDITING.md`) into `workspace/.skills/<name>/` so the agent can read and run them.
   Idempotent per session (the doc skills bundle ~MBs of schemas; copied once).

Wired into `core/agents.py: run()` — every specialist run selects + stages + injects skills
automatically. Exposed at `GET /api/skills`; visible in the UI Skills panel.

**Bundled skills:** `python-project` (write+test+run, edge cases), `web-frontend`
(responsive/accessible/polished), `research-report` (cited/decisive).
**Real Anthropic document skills:** `docx`, `xlsx`, `pptx`, `pdf` — these let the agent
**produce real Office/PDF files** by running bundled scripts. The Python libraries they need
(python-docx, openpyxl, python-pptx, reportlab, pdfplumber, pypdf, pandas, Pillow,
markitdown, defusedxml, lxml) are in `requirements.txt` and installed in `.venv`. Verified:
the toolchain produces real `.docx/.xlsx/.pptx/.pdf` files end-to-end.

**Add more skills:** `python scripts/import_skill.py <folder>` (e.g. clone anthropics/skills
and import one), then restart the server.

---

## 11. The web application — backend + frontend

### Backend (`server/`)
- **`app.py`** — FastAPI app; mounts every `api/*` router and serves the built React app
  from `web/dist`.
- **`db.py`** — SQLite via SQLModel. Tables: **Session** (id, title, project_id, starred,
  timestamps), **Message** (role, content, cost), **Event** (type + JSON data — the saved
  activity stream), **Checkpoint**; plus Memory/Job/Project tables registered by their
  modules. Uses **WAL mode + busy_timeout=30s** so the API and the background worker don't
  collide; `_migrate()` adds new columns to existing DBs additively. Owns the per-session
  **workspace** folders and the **checkpoint** snapshot/restore logic.
- **`chat.py: run_turn`** — the per-turn conductor (see §4): checkpoint → save → assemble
  context (history + memory recall + project + attachments) → `using_workspace` →
  `handle_task` → persist final + cost → `memory.remember` the outcome. Every event is saved
  to the DB and the trace as it streams.
- **`approvals.py`** — the security broker (see §9).
- **`api/ws.py`** — the live channel. On a `run` message it builds a `Budget` from the
  UI-supplied caps, makes an `ApprovalBroker` with the chosen mode, and runs the turn in a
  **daemon thread**; events bridge to the async socket through a thread-safe
  `asyncio.Queue`. `approval_response` resolves a pending human prompt; **`stop`** sets
  `budget.max_iterations = iterations` so the next `check()` halts the run cooperatively.
- **`api/sessions.py`/`messages.py`/`workspace.py`/`models.py`/`projects.py`/`jobs.py`** —
  the REST surface (CRUD, files+diff+versions+upload, model tiers/catalog/scout/skills/
  agents, projects, queue).
- **`memory.py`** (cross-session recall), **`trace.py`** (JSONL + optional Langfuse),
  **`jobs.py`** (persistent queue + worker), **`projects.py`** (shared instructions/files).

### Frontend (`web/`, React 18 + TS + Vite + Tailwind + Zustand)
- **`App.tsx`** — the shell: three-pane layout, Ctrl/⌘+K new chat, settings, dark mode.
  Design is the warm/editorial "Agent//Core" look (Geist / Source Serif / JetBrains Mono).
- **`components/`**:
  - **Chat.tsx** — message thread (markdown), the **live agent-activity timeline** (route /
    plan-todos / assign / thought / tool / critic / skill / approval), code blocks
    (CodeBlock.tsx, highlighted + copyable), diagrams (Mermaid.tsx), message
    copy/regenerate/edit, 👍/👎.
  - **Composer.tsx** — input + toggles (Plan-first, QA review, Parallel, Stream, approval
    mode) + attach; slash commands (/new /export /model /mode /help).
  - **Sidebar.tsx** — sessions (create/switch/rename/delete), search, star, Projects.
  - **RightPanel.tsx** tabs: **FilesPanel** (source / preview / diff / version history),
    **CheckpointsPanel** (rewind), **SkillsPanel** (all skills + which applied),
    **ModelRail** (live model swap), **JobsPanel** (background queue).
  - **ProjectModal / SettingsModal**.
- **`lib/store.ts`** — Zustand store (sessions, live-run events, toggles).
- **`lib/api.ts`** — REST client + the run-WebSocket hook.

---

## 12. Cost-first models + the model-scout
- **Cost-first** is the `cheapest` strategy in §5.2: cheapest **available + capable** model,
  task-aware. Adding a free key (NVIDIA NIM, OpenRouter `:free`, Gemini free, Ollama)
  unlocks free models automatically. Currently configured: NVIDIA NIM free for tier1/2,
  DeepSeek-R1 (free) for tier3; Gemini available as an option.
- **The model-scout** (`config/agents.yaml` + `POST /api/models/scout`) is the *only* part
  that uses an LLM to research current cheap/free/open models; it proposes catalog entries
  which you review and apply via `POST /api/models/catalog` (persisted to
  `models.discovered.yaml`). The picker itself is deterministic and free.

## 13. Memory, tracing, the job queue, MCP, images, evals
- **Memory** (`server/memory.py`): after each turn it stores "Request → Outcome"; on a new
  turn `recall()` pulls the top-k relevant notes from **other** sessions into context. Uses
  embeddings if `EMBED_MODEL` is set, else a lexical match. Emits a **`memory`** event.
- **Tracing** (`server/trace.py`): every event is appended to `data/traces/<session>.jsonl`;
  forwards to Langfuse if its keys are set.
- **Job queue** (`server/jobs.py`): `POST /api/enqueue` stores a job in SQLite; a worker runs
  it unattended (survives restarts); `GET /api/jobs/{id}` reports status.
- **MCP** (`tools/mcp.py` + `config/mcp.yaml`): a real stdio JSON-RPC client that connects to
  external MCP servers and registers their tools into the toolbelt (granted to agents you
  list). A tiny example server is bundled for testing (granted to no agent by default).
- **Images** (`tools/image.py`): the `generate_image` tool, gated on an `image_model:` +
  provider key.
- **Evals** (`evals/`): `python -m evals` runs a fixed task set (`cases.yaml`) through the
  real pipeline and grades each on **concrete yes/no** criteria (file exists? command exits
  0? expected words present?) — never a 1–10 score. `--dry-run` (offline), `--compare A B`
  (swap-safety diff), non-zero exit under the threshold (CI gate).

---

## 14. The event contract (every event type)

Every pipeline stage `emit`s a dict with a `type`. The UI renders these and the DB saves
them. Keep names stable; add a UI case if you add one.

`route` (carries `task_type`, never a bare `type`) · `plan` (carries `todos`) · `assign`
(a specialist picked, carries `skill?`) · `thought` · `tool` · `final` · `limit` · `error` ·
`manager_review` · `approval_request` · `blocked` (policy) · `denied` (approver) ·
`stopping` · `run_complete` · `critic` (QA pass/fail) · `token` (streamed final deltas) ·
`agent_token` (per-agent streamed tokens when stream=True) · `memory` (recalled notes) ·
`skill` (skills applied). `done` is an internal agent-finished marker.

---

## 15. The config files (what you edit)
- **`config/models.yaml`** — tiers (label/model/max_tokens), `defaults.model_strategy`
  (`cheapest`/`fixed`), and the **catalog** (per model: `requires_env`, `free`, `cost`,
  `tier_hint`, `good_for`). The optional `image_model:` lives here too. **This is the model
  swap point.**
- **`config/agents.yaml`** — one block per agent (tier, tools, capabilities, when_to_use,
  prompt, optional `max_usd`/`max_iterations`). **Add an agent here.**
- **`config/policy.yaml`** — `hard_block` (always blocked) + `require_human` (always needs
  your click) regex patterns. **Tune security here.**
- **`config/mcp.yaml`** — external MCP servers + which agents may use their tools.

## 16. What you must provide (placeholders) — full list in `docs/PLACEHOLDERS.md`

| To unlock… | Provide | Status |
|---|---|---|
| Real model runs | a provider key (you have **NVIDIA NIM**, free) | ✅ working |
| More free models / a fallback | `GEMINI_API_KEY` in `.env` | ⏳ you'll provide |
| Research web search | `SEARCH_API_KEY` (Tavily/SerpAPI) | ⏳ you'll provide |
| Image generation | `image_model:` in models.yaml + provider key | ⏸ parked |
| Embedding-backed memory | `EMBED_MODEL` + key (else lexical) | ⏸ skipped for now |
| Cloud tracing | `LANGFUSE_*` keys (local traces work now) | optional |
| Real MCP connectors | entries in `config/mcp.yaml` | optional |

## 17. How we compare to OpenClaw (openclaw.ai)
Both run locally, are model-agnostic, multi-agent, support skills + memory, and touch files.
**OpenClaw** is a *personal life assistant* reached from **messaging apps** (WhatsApp/
Telegram/Slack), running **24/7 proactively**, with **full browser control** and
**self-modification** — a mature, MIT-licensed product. **This app** is a *work/coding
cockpit* in a browser, built for **control + safety + craft**. Its edge over OpenClaw: the
**layered approval/security gate** + permission modes, the **artifact workbench** (preview/
diff/version history), **checkpoints/rewind**, **strict per-run cost caps**, **built-in QA**,
**plan-first approval**, **full transparency** (live timeline + audit log + traces), and
**config-driven extensibility** + an eval harness. OpenClaw's edge over this app: messaging
front-ends, real browser driving, always-on proactivity, self-modification, maturity.
One line: **OpenClaw bets on autonomy + reach; this app bets on control + safety.** (More in
`docs/COMPETITIVE.md`.)

## 18. The invariants + lessons learned
**Invariants (never break):** (1) never hardcode a model name in `core/`/`server/` — use the
registry; (2) every model call goes through `core/llm.py` and enforces the Budget; (3) every
run carries a Budget (`max_usd` + `max_iterations`) — no uncapped loops/spend; (4) `core/`
stays provider-agnostic + offline (no SDKs/web/model-strings/UI); (5) tools stay sandboxed
to the session workspace; (6) new pipeline stages must `emit` events.
**Lessons (don't reintroduce):** don't bake model names/prices into code/docs; QA judges on
**concrete pass/fail**, never a 1–10 score; don't run **dependent** coding subtasks "in
parallel" (you can't test before code exists); always treat web/file/email content as
**data, not instructions**.

## 19. How to verify nothing is broken
```
.venv\Scripts\python.exe scripts/smoke_test.py    # 26 offline checks (fake model, no cost)
.venv\Scripts\python.exe -m evals --dry-run       # validate the eval harness offline
```
The smoke test exercises the policy gate, the master loop (todos + delegation), QA
auto-review, skill selection + injection (incl. the document skills), sub-budgets, and the
server (REST + queue + diff + memory). All should pass (26/26).

## 20. What's done / what's left
**Done & verified:** the engine, the three registries, the supervisor + master loop, the
full layered security gate, SQLite persistence, the WebSocket live channel, the React app,
cost-first free models, the model-scout, cross-session memory, tracing, the job queue, the
MCP adapter, the eval harness, Agent Skills, and the real document skills (Word/Excel/
PowerPoint/PDF). Plus the Claude-parity polish: attachments, message-edit/branch, Projects,
Mermaid, settings, shortcuts, favorites, feedback, responsive layout, per-file version
history, streaming-by-default, auto-QA, the Skills panel.
**No outstanding no-key work.** Remaining items are **optional and need a key** (web search,
image gen) or are **future ideas** borrowed from OpenClaw (a Telegram/Slack front-end,
browser control). **Intentionally out of scope:** login / accounts / multi-user (single-user
local app).

---

_If you are a future chat reading this cold: the app is complete and runs at
`http://localhost:8800` from the `.venv`. Read §4–§10 to understand
the architecture, §11 for the app, §9 for security. The next concrete work only starts when
the user asks — likely wiring a key they provide (Gemini / search) or a new front-end. Don't
break the §18 invariants. **Also read the LATEST ADDITIONS section below — it supersedes
earlier sections where they differ.**_

---

## LATEST ADDITIONS (2026-06-03) — security, 4-type memory, coding harness, Model Lab

A large session after a full code review. This section is authoritative where it differs
from earlier text. Per-issue detail: `docs/REVIEW_FIXES.md` (security) and
`docs/MEMORY_DESIGN.md` (memory). Verified by a 60-check offline smoke test
(`python scripts/smoke_test.py`), strict TypeScript build, and live API checks.

**1. Security hardening (the app is now safe to expose, not just run locally).**
- `server/auth.py` — auth gate on **every** REST router + the WebSocket. If
  `AGENT_AUTH_TOKEN` is set it's required (Bearer / `X-Auth-Token` / `?token=`); if unset,
  the API answers **loopback only** and refuses other hosts. (Set the token in the UI:
  Settings → Access token.) `/api/health` + the SPA shell stay public by design.
- `tools/web.py` — **SSRF guard**: `web_fetch`/`web_search` resolve the host and reject
  loopback/private/link-local/metadata IPs, and re-validate on every redirect.
- `server/db.py:safe_id` — UUID-validates `session_id`/`checkpoint_id`/`project_id` before
  any filesystem join (a global `InvalidId→400` handler); blocks path traversal and the
  destructive `restore_checkpoint` rmtree.
- Budgets: client-supplied `max_usd`/`max_iterations` are clamped to
  `AGENT_MAX_USD_CEILING`/`AGENT_MAX_ITER_CEILING`; plus a **global daily spend cap**
  `server/spend.py` (`AGENT_DAILY_USD_CAP`, `/api/spend`, shown in Settings).
- `run_bash` is `RISK_CRITICAL` + `requires_human=True`, with an `AGENT_DISABLE_BASH`
  kill-switch (the Docker image sets it on). MCP tools default fail-safe to critical+human.
- Frontend: the `.svg` artifact preview renders in a **script-disabled sandboxed iframe**
  (was raw `dangerouslySetInnerHTML` = stored XSS); a single fetch wrapper checks
  `response.ok` and surfaces errors; the WebSocket closes on session switch + handles drops;
  message keys are stable; theme lives in the store (persisted); TS `strict` is on.

**2. Memory — all four types (`server/memory.py`, `server/chat.py`, `server/api/memory.py`).**
Context is assembled in `chat.run_turn` highest-value-first, each block bounded:
- **Working** — the last 12 messages verbatim + a rolling per-session **summary** of older
  turns (one cheap tier1 call when the window overflows).
- **Episodic** — `recall()` of notes from past chats; **lexical** by default, **embedding**
  (semantic) when `EMBED_MODEL` is set (`MEMORY_SEMANTIC_THRESHOLD` tunable).
- **Semantic facts** — durable facts auto-extracted from your messages (tier1, gated),
  deduped by key, injected into every chat. Viewable/editable/forgettable in the **Memory
  panel** (right-panel tab) + `/api/memory`.
- **Procedural rules** — on substantive turns the agent **proposes** a reusable rule; it is
  **never followed until you approve it** in the Memory panel; approved rules are injected as
  operating instructions. `/api/memory/rules`.
All extra calls are cheapest-tier, gated, budget-capped, and best-effort (never break a turn).

**3. Coding harness upgrade ("Path B" — Claude-Code-style coding on any cheap model, no proxy).**
- New **`edit_file`** tool (`core/tools.py`): exact-snippet replace with a diff returned to
  the model — agents no longer overwrite whole files. Granted to coder/frontend/lead.
- Coder/frontend/lead prompts rewritten to **explore → read-before-edit → edit precisely →
  run/verify → fix**. Per-agent tool-round cap raised 8→14 (`AGENT_MAX_TOOL_ROUNDS`).

**4. Model Lab — benchmark & compare models (`server/benchmark.py`,
`scripts/run_benchmark.py`, `evals/benchmark.yaml`, `server/api/benchmark.py`, "Bench" modal).**
Score any model on a 10-task battery across **coding / reasoning / writing / instruction**
aspects, in **raw** (model only) and **pipeline** (model+orchestration) modes, graded on
**concrete pass/fail** (never 1-10). Runs in an **isolated subprocess** (own scratch
workspace + forced model) so it never disturbs the live app/registry/sessions; refuses
gracefully if the model's provider key isn't set. Compare table in the UI. Pairs with the
model-scout: discover a new model → benchmark it → add winners to the catalog.

**5. Ops.** `scripts/backup.py` zips all stateful data (DB + workspaces + checkpoints).

**New env vars (all OPTIONAL for personal/local use; defaults are safe):** `AGENT_AUTH_TOKEN`,
`AGENT_DAILY_USD_CAP`, `AGENT_DISABLE_BASH`, `AGENT_MAX_USD_CEILING`, `AGENT_MAX_ITER_CEILING`,
`AGENT_MAX_TOOL_ROUNDS`, `MEMORY_MAX_SCAN`, `MEMORY_SEMANTIC_THRESHOLD`, `MAX_CHECKPOINTS`.
Full checklist + the one thing still required from the user (a provider key): `docs/PLACEHOLDERS.md`.
