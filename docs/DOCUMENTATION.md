# AGENT // CORE — Full Documentation

A local, extensible **multi-agent platform** with a chat UI — think a self-hosted
Claude Code / Cowork. Give it a goal; a supervisor breaks it down and routes each
piece to the right specialist agent; agents collaborate, use tools under a layered
security gate, and produce files you can preview. Models, agents, and tools are all
**config-driven and swappable** without touching code.

- New here? Read this top to bottom.
- Want the feature checklist? See [`../STATUS.md`](../STATUS.md).
- Want the competitive research + rationale? See [`COMPETITIVE.md`](COMPETITIVE.md).

---

## 1. The big picture

```
 BROWSER (React) ──REST──▶ FastAPI ──▶ Supervisor ──▶ specialist agents
        ▲     ▲                │            │              │ (each: allowed tools only)
        │     └──WebSocket─────┘            ▼              ▼
   files/chat  (stream + approvals)   SQLite + workspace   LiteLLM ▶ model providers
```

Three ideas make it extensible:
1. **Models** swap via `config/models.yaml`.
2. **Agents** are declared in `config/agents.yaml` (role, model tier, allowed tools, when-to-use).
3. **Tools** are registered in `core/toolbelt.py` (+ network tools from `tools/`), each with a risk label.

A new agent or capability is a config edit, not a code change.

---

## 2. How one chat turn works

1. You type a message in the UI; it's saved (SQLite) and a **WebSocket** opens.
2. A **workspace checkpoint** is snapshotted (so you can rewind this turn).
3. `server/chat.py` adds recent history as context and calls the supervisor.
4. **Router** (`core/router.py`) classifies difficulty (tier 1–3).
   - **Simple** → the **dispatcher** picks one specialist; it runs.
   - **Hard** → the supervisor **decomposes** into ordered subtasks; for each, the
     dispatcher picks a specialist; results are posted to the shared **blackboard**
     that later agents read; finally everything is **synthesized**.
5. Each agent runs the **agent loop** (`core/agent.py`): think → call tools → observe.
   Every tool call passes the **security gate** (below).
6. Events stream to the browser live (`route/plan/assign/thought/tool/final/…`) and
   are persisted. The final answer + cost are saved; the artifacts land in the
   session's workspace and the Files panel refreshes.

---

## 3. The agents (config/agents.yaml)

| Agent | Tools | Use it for |
|---|---|---|
| `supervisor` | — | decompose a complex goal (internal) |
| `general` | read/write/list | general Q&A, writing, analysis |
| `coder` | read/write/list/run_bash | write, run, debug code |
| `frontend` | read/write/list/run_bash | HTML/CSS/JS/React (live-previewable) |
| `research` | web_search/web_fetch/write | investigate, recommend (treats web as untrusted data) |
| `doc` | read/write/list | polished markdown/HTML documents |
| `image` | generate_image/write | images from a prompt |
| `critic` | read/list/run_bash | concrete pass/fail QA |
| `security-manager` | — | approve/deny risky actions (internal) |

**The dispatcher** (`core/agents.py:select_agent`) is shown a menu built from this
file and picks the best agent per subtask (cheap model call, keyword fallback). Add an
agent → it appears in the menu automatically.

---

## 4. Security model (layered)

Every tool call flows through escalating gates; the riskier it is, the more approval
it needs. It all hangs off the single `approve(tool, args, decision)` hook in the
agent loop, plus `core/policy.py`.

| Layer | Mechanism | Where |
|---|---|---|
| 0. Least privilege | each agent only has its allowlisted tools | `config/agents.yaml` |
| 1. Risk labels | tools tagged `safe`/`write`/`critical` + `requires_human` | `core/toolbelt.py` |
| 2. Policy gate | deterministic regex rules: hard-block / require-human | `core/policy.py` + `config/policy.yaml` |
| 3. Manager agent | `security-manager` approves/denies in context | `server/approvals.py` |
| 4. Human | Approve/Deny card in the UI | WebSocket + React |
| Audit | every call + decision appended to `audit.log` | `core/policy.py:audit` |

**Permission modes** (set in the composer or `/mode`):
- `auto` — manager agent + a human prompt only for irreversible actions.
- `careful` — manager agent + a human prompt for **every** risky action.
- `trusted` — auto-approve everything **except** hard-blocked patterns.

**Plan-first mode** (composer checkbox): the supervisor decomposes the goal, shows the
plan, and **stops**. A "Run this plan" banner appears; approving executes the approved
steps without re-planning (`orchestrator.handle_task(plan_only=True)` → resume with
`subtasks=[…]`).

Example — “delete the users table”: `run_bash` is `critical`, `DROP TABLE` matches a
require-human rule → policy escalates → manager agent reviews → **you** must Approve →
only then it runs, and the chain is logged. Hard-blocks (e.g. `rm -rf /`) never run.

---

## 5. Project layout

```
config/
  models.yaml        models per tier + UI catalog (+ optional image_model)
  agents.yaml        the agent registry
  policy.yaml        security rules (hard-block / require-human patterns)
core/                provider-agnostic engine (offline)
  llm.py             complete() + generate_image() — the ONLY provider calls + Budget
  registry.py        model registry (tier -> model)
  tools.py           sandboxed file/shell tools + per-session workspace
  toolbelt.py        tool registry (schema + risk + which agents)
  agent.py           generalized agent loop + approval hook
  policy.py          deterministic security gate + audit log
  agents.py          agent registry loader + dispatcher
  blackboard.py      shared per-run scratchpad
  router.py          difficulty classifier
  orchestrator.py    the supervisor
tools/               OPTIONAL network tools (web/image/mcp), register into toolbelt
server/
  app.py             FastAPI: API routers + serves web/dist
  db.py              SQLite (SQLModel) + workspaces + checkpoints
  chat.py            conversation manager (turn -> supervisor + history + persistence)
  approvals.py       manager-agent + human approval broker, permission modes
  api/               sessions, workspace, models/agents, ws (live run)
web/                 React + TS + Vite frontend (built to web/dist)
evals/               eval harness (python -m evals)
data/                SQLite db + per-session workspaces + checkpoints (created at runtime)
```

---

## 6. Running it

```bash
python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
cp .env.example .env          # add at least one provider key (e.g. ANTHROPIC_API_KEY)

npm --prefix web install      # one-time
npm --prefix web run build
uvicorn server.app:app --reload --port 8000        # open http://localhost:8000
```

**Frontend dev with hot reload:** `npm --prefix web run dev` (port 5173) alongside
uvicorn — Vite proxies REST + WebSocket to :8000.

**Optional capabilities (placeholders):** see `.env.example` — `SEARCH_API_KEY` for web
search, `image_model:` in `models.yaml` for the image agent.

---

## 7. Extending it

**Add an agent** — append to `config/agents.yaml`:
```yaml
  - id: data-analyst
    label: Data Analyst
    tier: tier2
    tools: [read_file, write_file, run_bash]
    capabilities: [data, analysis, csv]
    when_to_use: "Analyze datasets / CSVs and produce charts or summaries."
    prompt: |
      You are a data analyst. ...
```
That's it — the dispatcher will start routing matching work to it.

**Add a tool** — register it (offline tools in `core/toolbelt.py`; network tools in a
new `tools/<name>.py` that imports `core.toolbelt`):
```python
from core import toolbelt
def my_tool(x: str) -> str: ...
toolbelt.register_fn(
    "my_tool", my_tool,
    {"type":"object","properties":{"x":{"type":"string"}},"required":["x"]},
    "What it does.", toolbelt.RISK_WRITE,            # or RISK_SAFE / RISK_CRITICAL
)
```
Then grant it to an agent via that agent's `tools:` list.

**Connect an MCP server** — add it to `config/mcp.yaml`; its tools register as
`mcp__<server>__<tool>`, labelled with the given risk and granted only to the listed
agents:
```yaml
servers:
  - name: github
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    risk: write
    requires_human: false
    agents: [coder, research]
```
A bundled `example` server (echo/add) is wired by default so you can see it working.

**Swap a model** — edit `config/models.yaml` (or use the UI rail / `/model tier3 <id>`).

**Tighten security** — add patterns to `config/policy.yaml` (`hard_block` /
`require_human`) or flip a tool's risk label / `requires_human` in `toolbelt.py`.

---

## 8. API reference (server/)

REST:
- `GET  /api/health`
- `GET  /api/models`  ·  `POST /api/models/tier {tier, model}`
- `GET  /api/agents`
- `POST /api/sessions {title}`  ·  `GET /api/sessions`  ·  `GET/PATCH/DELETE /api/sessions/{id}`
- `GET  /api/sessions/{id}/messages`
- `GET  /api/sessions/{id}/files`  ·  `GET /api/sessions/{id}/file?path=…`
- `GET  /api/sessions/{id}/changes`  ·  `GET /api/sessions/{id}/file/diff?path=…` (vs last checkpoint)
- `GET  /api/sessions/{id}/checkpoints`  ·  `POST /api/sessions/{id}/restore {checkpoint_id}`
- `POST /api/enqueue {session_id, text, max_usd?, max_iterations?}`  ·  `GET /api/jobs[?session_id]`  ·  `GET /api/jobs/{id}` (background task queue)

WebSocket `/api/ws/{session_id}` — client→server:
- `{"type":"run","text":"…","max_usd":0.5,"max_iterations":12,"mode":"auto"}`
- `{"type":"approval_response","id":"…","allowed":true}`
- `{"type":"stop"}`

Server→client events (also the internal `emit` contract):
`route`, `plan`, `assign`, `thought`, `tool`, `final`, `limit`, `error`,
`manager_review`, `approval_request`, `blocked`, `denied`, `stopping`, `run_complete`,
`critic` (QA pass/fail verdict), `token` (streamed final-answer deltas),
`memory` (notes recalled from past chats), `agent_token` (per-agent streamed tokens).
(`route` carries `task_type`, never a bare `type`.) **Inputs you can add later are
listed in [`PLACEHOLDERS.md`](PLACEHOLDERS.md).**

---

## 9. Data & persistence
- `data/app.db` — SQLite (sessions, messages, events, checkpoints, memory).
- **Memory:** each turn's outcome is saved (`server/memory.py`); a new turn recalls the
  most relevant past notes (offline lexical scorer) and injects them as context.
- `data/workspaces/<session_id>/` — each chat's files (the artifacts).
- `data/checkpoints/<session_id>/<id>/` — workspace snapshots for rewind.
- `audit.log` — append-only record of every tool call + gate decision.

Delete `data/` to reset everything (chats + files + checkpoints).

---

## 10. Invariants (do not break — see CLAUDE.md)
- No model names in `core/` or `server/` — resolve through the registries.
- All model/image calls go through `core/llm.py`; network *tools* live in `tools/`.
- Every run carries a `Budget` (cost + iteration caps).
- Tools stay sandboxed to the (per-session) workspace.
- New pipeline stages must `emit` events.

## 11. Troubleshooting
- **“frontend isn't built”** at `/` → run `npm --prefix web run build`.
- **Real runs error / empty** → add a provider key to `.env` (e.g. `ANTHROPIC_API_KEY`).
- **web_search returns a placeholder** → set `SEARCH_API_KEY` (web_fetch works without).
- **image agent returns a placeholder** → set `image_model:` in `models.yaml` + a key.
- **Verify without keys** → `python -m evals --dry-run`.
