# GO-LIVE — verify the system against real models

The codebase is complete and passes 60 offline checks with a *fake* model. This page
is the short path to confirm it works with a *real* provider key, and what to watch for.

## 1. One-time setup
```bash
python -m venv .venv && source .venv/bin/activate   # (.venv\Scripts\activate on Windows)
pip install -r requirements.txt
npm --prefix web install && npm --prefix web run build
```
Put a real key in `.env` (only one is required):
```
GEMINI_API_KEY=AIza...          # the config is pre-wired for Gemini
```

## 2. Verify — three escalating checks
| Check | Command | Needs key | What it proves |
|-------|---------|-----------|----------------|
| Offline regression | `python scripts/smoke_test.py` | no | 60 checks: engine, platform, security, memory, API |
| **Live health** | `python scripts/live_smoke.py` | yes | a real model call + real router classification succeed |
| Live pipeline | `python -m evals` | yes | full tasks (route → agent → tools → grade); writes + runs a file |
| Run the app | `uvicorn server.app:app --port 8000` | yes | open http://localhost:8000 and chat |

Verified live on 2026-06-06 with Gemini: `live_smoke` 2/2; evals 2/3 (the one fail was
the free-tier rate limit on the judge call, not a code fault — see below).

## 3. Free-tier rate limits (the main gotcha)
Gemini's **free tier allows ~5 requests/minute per model**. A complex run (router +
planner + workers + QA + judge) can burst past that and get HTTP 429s. The pipeline
already retries (`num_retries=3`) and degrades gracefully, but for smooth runs:
- Use `scripts/live_smoke.py` (paced) for quick checks, and avoid firing many runs back-to-back.
- For real throughput, add a paid key, or add a **free NVIDIA NIM key** (`NVIDIA_NIM_API_KEY`,
  build.nvidia.com) — the cost-first selector will route harder tiers to it automatically.
- Optionally raise spacing: `LIVE_SMOKE_PACE=20 python scripts/live_smoke.py`.

## 4. Optional capabilities — add a key, restart, done
See `docs/PLACEHOLDERS.md`. Quick wins with the Gemini key you already have:
- **Semantic memory (free):** set `EMBED_MODEL=gemini/text-embedding-004` in `.env`.
- **Image agent:** uncomment `image_model: "gemini/imagen-3.0-generate-002"` in `config/models.yaml`.
- **Web search for research:** add `SEARCH_API_KEY` (Tavily/Serper).
- **Cloud tracing:** add `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` and `pip install langfuse`
  (the forwarder in `server/trace.py` now supports both the v2 and v3 SDK and flushes on shutdown).

## 5. Before exposing off localhost
Set `AGENT_AUTH_TOKEN`, set `AGENT_DAILY_USD_CAP` (e.g. `2.0`), keep `AGENT_DISABLE_BASH=1`
(Docker default) until shell runs in a real sandbox. Detail: `docs/REVIEW_FIXES.md`.
