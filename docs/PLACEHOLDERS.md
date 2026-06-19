# PLACEHOLDERS — everything that needs YOUR input

This is your one-stop checklist. The app **runs today with none of these** except one
provider key for real model calls (and even that isn't needed for the offline
`--dry-run` eval). Fill these in whenever you have time; each row says where it goes and
what it unlocks. **Nothing here blocks the parts already built.**

Legend: 🔴 needed for real model runs · 🟢 optional (feature already has a working
fallback or is off by default).

| # | What | Status | Where | Unlocks |
|---|------|--------|-------|---------|
| 1 | **A model provider API key** | 🔴 | `.env` | Real chats. Pick at least one: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, or `OPENROUTER_API_KEY`. **Currently wired for Gemini.** |
| 1b | **Free providers (cost-first)** | 🟢 | `.env` | The cost-first selector auto-uses **free** models once their key is set: `NVIDIA_NIM_API_KEY` (free, build.nvidia.com), `OPENROUTER_API_KEY` (for `:free` models), or `USE_OLLAMA=1` (+ run Ollama locally). Add one and hard tasks go free automatically. |
| 2 | **Web search key** | ✅ DONE | `.env`: `SEARCH_API_KEY` (+ optional `SEARCH_API_URL`) | The research agent's `web_search`. **Wired for Tavily and a key is set (2026-06-07) — working.** (`web_fetch` also works keyless.) Swap providers via `SEARCH_API_URL`. |
| 3 | **Image model** | 🟢 | `config/models.yaml`: `image_model:` + matching provider key in `.env` | The image agent's `generate_image`. |
| 4 | **Embedding model** | ✅ DONE | `.env`: `EMBED_MODEL` (or `embed_model:` in `config/models.yaml`) + provider key | **Semantic memory** — recall of past chats by *meaning* instead of keywords. **Set + working (2026-06-07): `EMBED_MODEL=gemini/gemini-embedding-001`** (+ `GEMINI_API_KEY`). NOTE: the older `gemini/text-embedding-004` is **retired/404** — use `gemini-embedding-001`. Falls back to keyword scoring if unset. |
| 5 | **Langfuse keys** | 🟢 | `.env`: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | Cloud tracing. Local JSONL traces (`data/traces/`) already work without it. *Also needs the `langfuse` SDK + finishing the stub in `server/trace.py:_forward_langfuse`.* |
| 6 | **Redis** (optional upgrade) | 🟢 | `.env`: `REDIS_URL` | Only if you outgrow the built-in SQLite task queue and want Redis/RQ. The current queue runs unattended without it. |
| 7 | **MCP servers** | 🟢 | `config/mcp.yaml` | Connect real external tools (GitHub, Slack, DB, browser…). Each server may need its own env (e.g. `GITHUB_TOKEN`). A bundled `example` server already works. |
| 8 | **Verify model names** | 🟢 (recommended) | `config/models.yaml` | Model strings go stale fast; confirm the tier1/2/3 models are current for your providers. |
| 9 | **Document-skill system tools** | 🟢 | install on your machine | The pdf/docx/xlsx/pptx skills work for most tasks with the **Python libs already in `requirements.txt`**. A few advanced paths want system tools: **LibreOffice** (`soffice`, for formula recalculation + PDF/format conversion), **pandoc** (docx↔markdown), and **Node.js** (the `docx-js` path for new Word docs). All optional — the Python paths (python-docx, openpyxl, python-pptx, reportlab) cover the common cases without them. |

## Security & limits — env vars added by recent builds (all OPTIONAL for personal/localhost use)

These were introduced by the security + memory work. **For personal use on your own
machine you can ignore every one of these** — the defaults are safe and the app already
answers only on localhost. They matter mainly if you ever expose it to a network.

| Env var | Default | What it does |
|---------|---------|--------------|
| `AGENT_AUTH_TOKEN` | unset | If set, every API/WebSocket call must send this token. If unset, the API answers **localhost only** and refuses other hosts. **Only needed if you expose the app off your machine.** Set it in the UI (Settings → Access token) too. |
| `AGENT_DAILY_USD_CAP` | `0` (unlimited) | **NEW.** Cumulative daily spend ceiling across all runs (a safety net above the per-run budget). e.g. `AGENT_DAILY_USD_CAP=2.0` stops new runs once you've spent $2 today (resets midnight UTC). Recommended once you add a paid key. |
| `AGENT_DISABLE_BASH` | unset (`1` in Docker) | Disables the shell tool entirely. Leave it off for local use (you approve shell commands anyway); turn it **on** for any networked deployment until you run shell inside a real sandbox. |
| `AGENT_MAX_USD_CEILING` | `5.0` | Hard per-run cost ceiling the UI can't exceed. Raise if you intentionally want pricier single runs. |
| `AGENT_MAX_ITER_CEILING` | `60` | Hard per-run loop ceiling the UI can't exceed. |
| `MEMORY_MAX_SCAN` | `2000` | How many recent memory rows a recall scans. Tuning only. |
| `MEMORY_SEMANTIC_THRESHOLD` | `0.60` | Similarity cutoff for Phase C embedding recall. Tuning only. |
| `MAX_CHECKPOINTS` | `20` | Per-chat workspace snapshots kept for rewind (older ones pruned). |
| `AGENT_MAX_TOOL_ROUNDS` | `14` | How many tool rounds a single agent gets before being forced to a final answer. Raised so multi-step coding (read→edit→run→fix) can finish; the per-run budget is still the hard ceiling. |
| `AGENT_SECRET_KEY` | unset | **NEW.** When set, the UI-managed API-key store (`data/keys.json`) is encrypted at rest (Fernet, key derived from this secret). Recommended for any internet-facing deployment. Backward-compatible: a legacy plaintext store still loads and is re-encrypted on the next save. Keep this value stable — changing it makes previously-stored keys unreadable (env-var keys still work). |
| `AGENT_COMPACT` | `1` (on) | **NEW.** Within-run context compaction: summarizes older turns when the history nears the context budget so long tasks don't hit the cap. Set `0` to disable. `AGENT_COMPACT_RATIO` (`0.8`) = fraction of the context budget that triggers it; `AGENT_COMPACT_KEEP` (`6`) = recent messages kept verbatim. |
| `AGENT_POSTEDIT_VERIFY` | `1` (on) | **NEW.** After write_file/edit_file, syntax-checks `.py`/`.json`/`.yaml` in-process and warns if the file is broken. Set `0` to disable. |
| `AGENT_TASK_SUBWORKSPACE` | `0` (off) | **NEW.** When `1`, a request that starts a fresh standalone build runs in its own sub-folder so unrelated projects in one chat don't collide. Off by default (everything in the session root). |
| `AGENT_READ_MAX_LINES` / `AGENT_READ_MAX_BYTES` | `2000` / `51200` | **NEW.** Caps on a single `read_file` (paged output; use offset/limit to continue). Tuning only. |

## Backups (no key needed)
Your only un-rebuildable data lives in `data/` (chats, memory, files, checkpoints).
Back it up anytime with **`python scripts/backup.py`** (→ `backups/agentcore-<timestamp>.zip`;
add `--keep 10` to auto-prune). Restore = stop the app, unzip over the project root, restart.

## How to apply
1. `cp .env.example .env` (if you haven't) and paste keys for rows you want.
2. Edit `config/models.yaml` for rows 3, 4, 8; `config/mcp.yaml` for row 7.
3. Restart `uvicorn`. That's it — features light up automatically when their input is present.

## Minimum to "use it for real"
Just **row 1** (one provider key). Everything else is additive.

## Notes
- All optional features **degrade gracefully**: research → `web_fetch` only; memory →
  keyword recall; tracing → local files; queue → SQLite. So a missing key never breaks a run.
- Costs are always capped by the per-run **Budget** (max $ + max loops), and risky
  actions still go through the **security gate** regardless of which keys are set.
- The only items that need a little *code* (not just a key) are the Langfuse forward
  stub (row 5) and a Redis/RQ swap (row 6); both are documented inline where they live.
