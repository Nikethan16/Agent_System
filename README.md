# AGENT // CORE

A small but solid multi-agent core. The architecture is fixed and strong; the
**models are fully swappable** — change one config line (or a dropdown) and the
whole pipeline uses a different model, across any provider.

This is the foundation. It does the hard part (routing, orchestration, the agent
loop, safety caps) cleanly, so you can grow it without rewrites.

---

## Why it's built this way

The single biggest weakness in most "AI company" designs is hardcoding model
names into the logic. Here, **no module names a model.** Everything asks the
registry, and the registry reads `config/models.yaml`. Swap freely.

Model calls go through **LiteLLM**, which normalizes 100+ providers to one
format. So `claude-opus-4-7`, `gpt-5.5`, `gemini/gemini-3.1-pro`,
`deepseek/deepseek-chat`, or a local `ollama/...` model are all the same call —
only the string changes.

---

## Placement (how the pieces fit)

```
agent_system/
├── config/
│   └── models.yaml        ← THE SWAP POINT. Tiers → models. Edit here.
├── core/                  ← provider-agnostic engine (no web, no model names)
│   ├── registry.py        ← loads models.yaml, resolves tier → model
│   ├── llm.py             ← the one unified model call + budget caps
│   ├── tools.py           ← agent tools (file/shell), sandboxed to workspace
│   ├── agent.py           ← the agent loop (think → act → observe)
│   ├── router.py          ← cheap classifier: task → tier
│   └── orchestrator.py    ← simple → 1 agent; hard → plan + subagents
├── server/
│   └── app.py             ← FastAPI: run tasks, stream events, swap models
├── ui/
│   └── index.html         ← mission-control panel (live + demo modes)
├── requirements.txt
└── .env.example
```

Data flow for one task:

```
task → router.classify → tier
            │
   tier 1/2 │ tier 3
            ▼            ▼
      1 worker      planner → subtasks → workers → synthesis
            └──────────────┬──────────────┘
                           ▼
                    final answer (+ total cost)
```

Every step streams an event to the UI, so you watch it happen.

---

## The app (multi-agent chat — like a local Claude Code / Cowork)

A complex goal is split by a **supervisor** and routed to specialist agents
(coder, frontend, research, doc, image, …) chosen by a **dispatcher**; agents
collaborate via a shared blackboard. You chat with it, watch the team work live,
**approve risky actions** (a security-manager agent + your click gate destructive
ops), and browse/preview the **files it produces**. Chats and files are **saved**.

Adding an agent is a few lines in `config/agents.yaml` — no code change. Connecting
a capability is registering a tool in `tools/`. Same config-driven philosophy as the
model swap.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add at least ONE provider key (see docs/PLACEHOLDERS.md)
```

Then, easiest (builds the frontend if needed and starts the server):

```powershell
.\run.ps1                     # Windows  → serves at http://localhost:8800
```
```bash
./run.sh                      # macOS/Linux
```

Or manually: `npm --prefix web install && npm --prefix web run build`, then
`uvicorn server.app:app --reload --port 8800`.

**Open → http://localhost:8800** (Docker maps to 8000). Start a chat; swap any tier's
model from the left rail. For live frontend dev with hot reload: `npm --prefix web run dev`
(port 5173, proxies to :8800) alongside uvicorn.

> **You need one model provider key** in `.env` for real runs (the app refuses nothing
> else, but without a key it can't call a model). Off localhost, also set
> `AGENT_AUTH_TOKEN`. Full checklist: `docs/PLACEHOLDERS.md`.

### Optional capabilities (PLACEHOLDERS — fill in to enable)
- **Research agent / web search:** set `SEARCH_API_KEY` (+ `SEARCH_API_URL`) in `.env`.
  `web_fetch` already works keyless; `web_search` needs a provider key.
- **Image agent:** set `image_model:` in `config/models.yaml` and the matching provider
  key in `.env`.
- **MCP connectors:** real stdio adapter — add servers to `config/mcp.yaml` and their
  tools appear as agent tools (a bundled `example` server works out of the box).
- **Plan-first mode & permission modes:** toggle "plan first" to preview/approve the
  plan before it runs; set approvals to auto/careful/trusted. Workspace **checkpoints**
  let you rewind.

---

## Swapping models (the whole point)

**Permanently:** edit `config/models.yaml`:

```yaml
tiers:
  tier3:
    model: "gpt-5.5"        # was claude-opus-4-7 — that's the entire change
```

**Per session:** use the dropdowns in the UI.

**One key for everything:** route through OpenRouter — set `OPENROUTER_API_KEY`
and use `openrouter/<vendor>/<model>` strings, then you never manage per-provider
keys again.

> Model names move fast (≈3 notable releases/day in early 2026). The strings in
> `models.yaml` are a starting snapshot — verify current ones at
> https://llm-stats.com or your provider's docs.

---

## Safety built in

- **Hard caps** — every run has a max cost (USD) + max loop count, plus a global
  **daily spend cap** (`AGENT_DAILY_USD_CAP`) above it. No runaway bills.
- **Auth gate** — with `AGENT_AUTH_TOKEN` set, every API/WS call needs it; unset,
  the API answers **localhost only** (so it can't be exposed wide-open by accident).
- **Layered approval** — least-privilege tool grants → deterministic policy gate →
  security-manager agent → human approve/deny. `run_bash` always asks a human and can
  be disabled with `AGENT_DISABLE_BASH=1`.
- **Sandboxed tools** — file/shell access is confined to the session workspace; ids are
  UUID-validated and `web_fetch` blocks private/metadata URLs. For a networked deploy,
  run `run_bash` inside a real container, not just a path check.
- **Graceful routing** — bad classifier output falls back to a safe tier.

---

## What's built (highlights)

Far past the lean core now. See `STATUS.md` for the full matrix and `docs/PROJECT_OVERVIEW.md`
for the complete account. In short:

- **Multi-agent platform** — 3 config-driven registries (models/agents/tools), a dispatcher,
  a Claude-Code-style supervisor (todos + delegation), a shared blackboard, Agent Skills.
- **Memory (4 types)** — working (rolling summary), episodic recall (lexical, or embeddings
  when `EMBED_MODEL` is set), semantic facts (auto-learned, editable in the UI), and procedural
  rules (agent proposes → you approve). See `docs/MEMORY_DESIGN.md`.
- **Coding harness** — surgical `edit_file`, explore→read→edit→verify prompts, longer tool loop.
- **Model Lab** — benchmark + compare any model across aspects (raw vs pipeline), concrete
  pass/fail scoring. Open the **"Bench"** button.
- **Security** — auth gate, layered approval, SSRF/path guards, per-run + daily spend caps,
  audit log. (See `docs/REVIEW_FIXES.md`.)
- **Ops** — eval harness (`python -m evals`), 60-check offline smoke test
  (`python scripts/smoke_test.py`), local JSONL traces, one-command backups
  (`python scripts/backup.py`).

**Only remaining for a public deployment** (not needed for personal/local use): a real
container sandbox for `run_bash`, the Langfuse forward stub, and multi-user accounts
(intentionally out of scope). Optional capabilities that need your keys are in
`docs/PLACEHOLDERS.md`.
```
