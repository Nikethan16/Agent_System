# AGENT // CORE — What This Application Can Do

_Last updated: 2026-06-15. A plain-language catalogue of everything the app is capable of
today, what's working right now vs. what needs a key, and its current limits. If you're
picking this project up fresh (or it's a new chat with no memory), read this for "what it
does", then `HANDOFF.md` for "current state + what's next", then `docs/PROJECT_OVERVIEW.md`
for "how it works under the hood"._

> **Now live (2026-06-15):** deployed 24/7 on an Oracle Always-Free VM, reached privately via
> Tailscale, with push-to-main CI/CD. The UI is a **Claude.ai clone** with **email+password
> login**, per-response **run summaries** (time/tokens/cost/tools/files with `+/-` line counts),
> a **5-tab Settings**, and a ⌘K command palette. Telegram phone control is live. Repo-engineer
> mode, Docker sandbox, Langfuse tracing, NumPy ANN memory index, trace-viewer panel, and a
> 55-case pytest suite all shipped 2026-06-15.
> See `docs/SETUP_GUIDE.md` (hosting) and `docs/BACKLOG.md` (what's left).

---

## In one paragraph

AGENT // CORE is a **private, local, browser-based AI work assistant** — like running your
own Claude Code / ChatGPT on your machine, using whichever AI models you choose (including
**free** ones). You chat with it; it plans the work, writes and runs code, builds real
documents (Word/Excel/PowerPoint/PDF), searches the web, remembers things across chats, and
shows every step live. It asks your permission before risky actions and **can never exceed a
dollar cap you set**. The defining design idea: anything that might change — the AI models,
the specialist agents, their tools — lives in **config files**, so you swap the model behind
the whole thing by changing one line.

---

## What it can do (capabilities)

### 1. Have a conversation
Chat naturally; it answers questions, explains things, and writes prose. Trivial messages
("hi") get a fast, clean reply with no machinery. It keeps multi-turn context within a chat.

### 2. Write, run, and debug code
A **coder** agent can explore a workspace, read files, make **surgical edits** (precise
snippet replacement, not blind overwrites), run shell commands, run the code/tests, see the
output, and fix what it wrote — the Claude-Code-style "explore → edit → run → verify" loop.
Each chat has its own **isolated workspace** under `data/workspaces/`.

### 3. Build a previewable web front-end
A **frontend** agent builds HTML/CSS/JS you can preview directly in the app's Files panel.

### 4. Produce real documents
Using the bundled **Anthropic document skills**, it creates genuine **Word (.docx), Excel
(.xlsx), PowerPoint (.pptx), and PDF** files — not just text. Verified end-to-end. (A few
advanced formatting paths optionally want LibreOffice/pandoc/Node; the common cases work
with the Python libraries already installed.)

### 5. Research the web ✅
A **research** agent can **search the web** (via Tavily) and **fetch & read pages**, then
write a cited summary. Fetched content is treated as untrusted **data**, never instructions
(a prompt-injection guard). _This was fixed and enabled on 2026-06-07 — see HANDOFF.md._

### 6. Remember across chats (4 kinds of memory)
- **Working** — recent messages + a rolling summary of older turns.
- **Episodic** — recalls relevant notes from *past* chats. Now **meaning-based** (semantic)
  using embeddings; falls back to keyword matching if no embedding model is set.
- **Semantic facts** — durable facts it auto-learns about you, injected into every chat,
  editable in Settings → Memory.
- **Procedural rules** — it *proposes* reusable rules; they only take effect **after you
  approve** them in Settings → Memory.

### 7. Orchestrate a team of specialist agents
Simple tasks go to one specialist. Hard tasks go to a **LEAD** agent that writes a to-do
list and **delegates** scoped steps to specialists (coder, frontend, research, doc, critic,
image), who share results through a blackboard. A **dispatcher** picks the right specialist
for each job. It's modeled on Claude Code's single-threaded master loop.

### 8. Check its own work (QA)
On substantive tasks a **critic** agent automatically reviews the result against **concrete
pass/fail criteria** (does it run? are requirements met?) — never a vague 1–10 score — and
sends it back once for a fix if it fails.

### 9. Keep you in control (layered safety)
Risky actions pass through: per-agent tool allowlists → a deterministic policy gate →
a **security-manager** AI review → **your** Approve/Deny click — all written to an audit log.
**Permission modes** per run: *auto* (ask only for irreversible), *careful* (ask every time),
*trusted* (auto-approve all but hard-blocks). Irreversible actions need both the manager AND
your click.

### 10. Never overspend
Every run carries a hard **dollar cap** and **step cap**. There's also an optional **daily
spend cap** across all runs. Nothing can loop or spend without a ceiling.

### 11. Swap the AI model freely
No model name is hardcoded. Pick models per difficulty tier in `config/models.yaml` or the
Settings → Models screen. **Cost-first mode** auto-picks the cheapest *capable + available*
model, so adding a free provider's key makes free models get used automatically. Works with
Google, OpenAI, Anthropic, NVIDIA NIM, OpenRouter, DeepSeek, or local Ollama — all through
LiteLLM.

### 12. Benchmark & compare models (Model Lab)
The **"Model Lab"** (in Settings → Models) scores any model on a task battery across
coding/reasoning/writing/instruction, in raw vs. pipelined modes, with concrete pass/fail —
so you can compare models before committing. A **model-scout** can research new cheap/free
models and propose catalog additions.

### 13. Undo and rewind
The workspace is snapshotted **before every turn**. You can rewind to an earlier state
(Right panel → Rewind), and view a per-file version history and diffs.

### 14. Organize work
- **Projects** — group chats with shared instructions + knowledge files.
- **Background tasks** — queue a task to run unattended (survives restarts).
- **Attachments** — drop in a file (PDF text is extracted) as context.
- **Export** — download any chat as Markdown.

### 15. Extend by configuration, not code
Add an **agent** (a YAML block), a **tool** (register it), or a **skill** (drop in a
`SKILL.md` folder) — no core code changes. Connect external tools via **MCP** servers.

### 16. Work on a GitHub repo end-to-end
A **repo-engineer** agent can clone a repo, create a branch, read/edit/run code in it,
commit, push, and open a pull request — all from a single chat prompt. Uses a `repo`
playbook (clone → plan → branch → implement → verify → push → PR). Push and PR require your
explicit approval. Repo content is treated as untrusted data (prompt-injection guard).
Needs `GITHUB_TOKEN` in `.env`.

### 17. Run shell commands in a hardened Docker sandbox
When `AGENT_BASH_DOCKER_IMAGE` is set, every `run_bash` call runs inside an **ephemeral
container** (cap-drop ALL, no-new-privileges, read-only filesystem + tmpfs, PID/memory/CPU
limits, killed on timeout) — no access to the host system. Without the image set, bash is
blocked entirely (fails closed). Tunable via `AGENT_BASH_DOCKER_TIMEOUT/MEMORY/CPUS/NETWORK/PIDS`.

### 18. Live trace viewer
The **Trace** tab in the right panel renders the span tree for every run: agent nodes,
tool calls, and LLM generations — each with cost, token counts, and duration chips.
Collapsible hierarchy; refreshes automatically when a run completes. Backed by
`GET /api/traces/{session_id}` which reconstructs the tree from the always-on local JSONL
(works on all existing traces without any write-path change).

### 19. File `+/−` line counts in run summaries
The response footer shows each changed file as `file.py +42 −8` (green/red) — computed
via unified diff of the workspace checkpoint vs. post-run state. Falls back to path-only
display for older messages that predate the feature.

### 20. Distributed tracing (Langfuse span tree)
Every run produces a **span tree**: run → subagent → LLM generation, each node carrying
model name, prompt + completion tokens, cost, and latency. Always-on as local JSONL files
in `data/traces/`. Optionally forwarded to **Langfuse** when `LANGFUSE_*` keys are set.
`core/` stays offline — it holds only a callback hook + a ContextVar; no provider import in core.

### 21. Fast semantic memory recall (NumPy ANN index)
Episodic memory and RAG retrieval now use a lazy in-memory **unit-normalized NumPy matrix**
for vectorized cosine search over the full corpus — no `_MAX_SCAN` ceiling. Invalidated
automatically on every memory write. Falls back to the Python cosine loop, then to lexical
search if NumPy is absent. Tunable via `MEMORY_VECTOR_BACKEND` (auto | numpy | none).

---

## What's working *right now* on this machine

Two **free** provider keys are configured (**Google Gemini** + **NVIDIA NIM**), so the app
runs at **$0**:

| Capability | Status |
|---|---|
| Chat, coding, documents, multi-agent, QA, security, memory, checkpoints, projects, jobs, Model Lab | ✅ Working |
| **Web search** (Tavily key set) | ✅ Working |
| **Semantic (meaning-based) memory** (Gemini embeddings + NumPy ANN index) | ✅ Working |
| **Repo-engineer** (clone/branch/edit/commit/push/PR) | ✅ Code done — needs `GITHUB_TOKEN` in server `.env` |
| **Docker sandbox** for shell commands | ✅ Image built on server — needs `AGENT_BASH_DOCKER_IMAGE` env var flip |
| **Langfuse cloud tracing** | ✅ Local JSONL always-on; needs `LANGFUSE_*` keys for cloud |
| **Trace viewer** (Trace tab, span tree) | ✅ Working |
| **File `+/−` line counts** in run footer | ✅ Working |
| Image generation | ⏸ Off — needs an image model + key (code is ready) |

## How to run it
```powershell
.\run.ps1                 # builds the web UI if needed, serves at http://localhost:8800
```
Verify offline (no key, no cost): `.venv\Scripts\python.exe scripts\smoke_test.py` → 60/60.

## Current limits / things to know
- **Free-tier rate limits** are the main friction (e.g. Gemini free ≈ a few requests/minute);
  big multi-step jobs can briefly pause. Retries now recover automatically (tenacity).
- **Tier-2/3 models must support tool-calling** or the coder/lead can only talk, not act.
- **Model names go stale fast** — verify the strings in `config/models.yaml` against your
  providers (we've already hit and fixed a couple of retired model names).
- **Single-user, local app** by design — no multi-user accounts (intentionally out of scope).
- For a networked deployment only: run the shell tool inside a real container sandbox.

## Where to read more
- `HANDOFF.md` — current state, what changed last, and what to do next (read this second).
- `docs/PROJECT_OVERVIEW.md` — the full technical account of how it works.
- `docs/UI_STRUCTURE_PLAN.md` — the UI design/structure.
- `docs/PLACEHOLDERS.md` — every optional key and what it unlocks.
- `CLAUDE.md` — the durable rules/invariants (auto-loaded each chat).
