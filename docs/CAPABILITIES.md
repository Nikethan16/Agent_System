# AGENT // CORE — What This Application Can Do

_Last updated: 2026-06-07. A plain-language catalogue of everything the app is capable of
today, what's working right now vs. what needs a key, and its current limits. If you're
picking this project up fresh (or it's a new chat with no memory), read this for "what it
does", then `HANDOFF.md` for "current state + what's next", then `docs/PROJECT_OVERVIEW.md`
for "how it works under the hood"._

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

### 5. Research the web ✅ (now working)
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

---

## What's working *right now* on this machine

Two **free** provider keys are configured (**Google Gemini** + **NVIDIA NIM**), so the app
runs at **$0**:

| Capability | Status |
|---|---|
| Chat, coding, documents, multi-agent, QA, security, memory, checkpoints, projects, jobs, Model Lab | ✅ Working |
| **Web search** (Tavily key set) | ✅ Working |
| **Semantic (meaning-based) memory** (Gemini embeddings) | ✅ Working |
| Image generation | ⏸ Off — needs an image model + key (code is ready) |
| Cloud tracing (Langfuse) | ⏸ Off — local trace files work; needs Langfuse keys |

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
