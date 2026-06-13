# HANDOFF — read this first

_Last updated: 2026-06-13. The single entry point for the next person/chat picking this up
(the prior chat may have been deleted). For "what it can do" read `docs/CAPABILITIES.md`;
for "how it works" read `docs/PROJECT_OVERVIEW.md`; the durable rules are in `CLAUDE.md`._

## TL;DR
- **Big optimization pass landed on branch `feat/platform-optimization`** (8 commits, NOT yet
  merged to `main`). Offline smoke **60→107**; web build clean; fleet endpoints verified live.
- **What's new this session:** multi-key **resilience engine** (key pool + per-call timeout +
  NVIDIA-first **fallback chains**, so a rate-limited/dead model self-heals); the full **NVIDIA
  NIM fleet** (DeepSeek V4 Pro orchestrates, GLM-5.1 codes, Qwen researches, Nemotron reasons)
  + 4 new roles (architect/data-analyst/code-reviewer/fast-coder); **memory continuity**
  (resumable Project State + adaptive context window — the hardcoded 12-message window is gone);
  a **scheduler** (`/api/schedules`); **Telegram** mobile control; **parallel sub-agents**
  (`delegate_parallel`); a **management UI** (Settings → Fleet & keys, Schedules); and **CI**.
- **Two free keys** in `.env` (Gemini + NVIDIA NIM) → runs at **$0**. Add more NVIDIA accounts
  as `NVIDIA_NIM_API_KEY_1..N` (or via Settings → Fleet) to multiply throughput.
- **Owner inputs still pending (placeholders left):** `TELEGRAM_BOT_TOKEN` (+ allowlist) for
  the phone bot; optional extra NVIDIA keys for the pool. See `.env.example`.
- **Not yet built (needs decisions/inputs):** multimodal/vision input, doc-parser & content-
  safety NIM microservices (the 🔴 items) — they need a sample use-case + small plumbing.
- Run it: `.\run.ps1` → http://localhost:8800. Verify: `.venv\Scripts\python.exe scripts\smoke_test.py` (107/107).

## What changed in the last working session (2026-06-07)
All verified; smoke stays 60/60; the web build is clean.

1. **Web search now actually works.** `tools/web.py:web_search` was a broken stub (unreachable
   return + wrong request shape). Rewrote it for **Tavily** (correct request, result
   formatting, kept the SSRF guard + untrusted-data wrapper). A free Tavily key is set as
   `SEARCH_API_KEY` in `.env`. Verified end-to-end (raw + through the research agent).
2. **Fixed a missing dependency: `tenacity`.** LiteLLM's retry/backoff path imports it, but it
   wasn't installed or in `requirements.txt`, so every rate-limit retry crashed. Added +
   installed. This restores free-tier resilience (retries now recover instead of crashing).
3. **Fixed a dead tier-3 model.** `nvidia_nim/deepseek-ai/deepseek-r1` now 404s on NVIDIA NIM
   (it was the cost-first pick for tier-3, so research/hard tasks crashed). Swapped to the
   verified-working **`nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5`** (free, reasoning,
   supports tool-calling) in `config/models.yaml`.
4. **Enabled semantic memory.** The docs' suggested embedding model (`text-embedding-004`) was
   retired/404. Set `EMBED_MODEL=gemini/gemini-embedding-001` in `.env` (verified it produces
   meaningful embeddings; similar sentences score ~0.76 vs ~0.46 for unrelated).
5. **Made the smoke test hermetic** (`scripts/smoke_test.py`) — it reused a persistent data dir
   and leaked approved rules between runs; now it starts fresh each run.
6. **UI redesign integrated** (from a Google Stitch design — see `docs/UI_STRUCTURE_PLAN.md`).
   A structural declutter, no backend changes, all wiring preserved:
   - **Composer** is now minimal: type · attach · send, plus a **"Run options" popover** that
     holds approval mode, plan-first, force-QA, parallel, stream, and per-run max $/loops.
   - **Top bar** slimmed to status · run cost · settings (Export + Model Lab moved into Settings).
   - **Right panel** down from 6 tabs to **4** (Files, Rewind, Skills, Tasks) with count badges;
     **Memory** and **Models** moved into Settings.
   - **Settings** is now a **5-tab** modal (General, Limits & cost, Models, Memory, Security).

> Lesson reinforced this session: **model strings (chat, embedding, and reasoning) go stale
> fast.** We hit three retired names. When something 404s, list the provider's current models
> (`/v1/models`) and update `config/models.yaml` / `.env`.

## Current state by area
| Area | State |
|---|---|
| Engine, platform, security, memory, persistence, jobs, tracing | ✅ done |
| Web search (Tavily) · semantic memory (Gemini embeddings) | ✅ working |
| UI (decluttered redesign) | ✅ integrated + built |
| Image generation | ⏸ off — code ready, needs an image model + key |
| Cloud tracing (Langfuse) | ⏸ off — local traces work; needs keys |
| Production hardening (exposed deploy) | 🟡 partial — see "deployment" below |

## What's LEFT (optional — nothing blocking)
**A. UI polish not yet done (low priority):** the right panel auto-collapsing to a badge-only
rail, and a command palette (⌘K currently just opens a new chat). Core declutter is done.

**B. In-code, no inputs needed:** make the Docker host port configurable (don't hardcode);
broaden tests beyond the 60-check smoke.

**C. Needs the owner (keys/decisions, all optional):** a *paid* model key (removes free-tier
rate limits), an `image_model:` + key (image gen), `LANGFUSE_*` keys (cloud tracing). See
`docs/PLACEHOLDERS.md`.

**D. Deployment-only (before exposing off localhost):** run `run_bash` inside a real container
sandbox (keep `AGENT_DISABLE_BASH=1` until then).

**E. Intentionally out of scope:** multi-user accounts (single-user local app by design).

## How to run & verify
```powershell
.\run.ps1                                       # serves http://localhost:8800
.venv\Scripts\python.exe scripts\smoke_test.py  # offline, 60/60, no key
```
The frontend is built into `web/dist`; the backend serves it. For UI dev with hot reload:
`npm --prefix web run dev` (port 5173, proxies to 8800) alongside the server.

## Context for the next chat (don't re-discover these)
- **`.env` already has working keys** (gitignored, never pushed): `GEMINI_API_KEY`,
  `NVIDIA_NIM_API_KEY`, `SEARCH_API_KEY` (Tavily), `EMBED_MODEL=gemini/gemini-embedding-001`.
  The ANTHROPIC/OPENAI/DEEPSEEK/OPENROUTER vars are 1-char placeholders (not real).
- **The Python venv is `.venv`** — run things as `.venv\Scripts\python.exe …`. If a shell's
  working dir drifts (e.g. after `cd web` to build), use the absolute venv path.
- **GitHub:** the repo is **github.com/Nikethan16/Agent_System** (private). Commit identity for
  this repo is `Nikethan <nikethan160902@gmail.com>` (set repo-locally; the machine's *global*
  git is a different work identity and was intentionally left unchanged — don't touch it).
  `gh` CLI is **not** installed — pushes use Git Credential Manager (a browser sign-in may pop
  up the first time).
- **Owner's git preferences:** do **not** add a Claude co-author trailer; split work into
  logical, version-wise commits.
- **Respect the invariants in `CLAUDE.md`:** no hardcoded model names (use the registry);
  every model call via `core/llm.py` under a Budget; tools sandboxed to the session workspace.

## How to resume
1. `cd C:\Project\agent_system && claude` (auto-loads `CLAUDE.md`).
2. Read `docs/CAPABILITIES.md` (what it does) → this file (state) → `STATUS.md` (detail).
3. After any change: `python scripts\smoke_test.py` (keep 60/60) and update `STATUS.md`.
