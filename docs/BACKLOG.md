# BACKLOG — what's left to do

_Last updated: 2026-06-15. The prioritized list of remaining work. Nothing here is blocking —
the app is complete and deployed live. Items are roughly ordered by value. See `HANDOFF.md`
for current state and `STATUS.md` for what's already done._

---

## ✅ Recently shipped (2026-06-15) — repo mode, Docker sandbox, tracing, ANN index
These four were built and pushed (branch `claude/serene-lamport-r1ix0k`, commit `513eb24`).
Code is done; the items below note the **operational steps** still needed to activate them live.

- **"Work on a repo" mode** — `tools/github.py` (git_clone/status/diff/log/checkout/commit/push +
  create_pull_request via GitHub REST), a `repo-engineer` agent (`config/agents.yaml`), and a
  `repo` playbook (clone→plan→branch→implement→verify→push→pr). PR/push are `requires_human`.
- **Docker shell sandbox (hardened)** — `core/tools.py`: host-shell fallback removed (fails closed),
  hardened `docker run` (cap-drop, no-new-privileges, read-only, tmpfs, pids/mem/cpu limits, timeout
  cleanup). `run_bash` drops to RISK_WRITE when `AGENT_BASH_DOCKER_IMAGE` is set (no human click).
- **Langfuse distributed tracing** — `server/trace.py` rewritten into a span tree (run → subagent →
  LLM generation with model/token-split/cost/latency). Offline JSONL still always-on. core stays
  offline via a callback hook + ContextVar in `core/llm.py`.
- **ANN vector index** — `server/vectorstore.py` (NumPy matrix, full-corpus, no `_MAX_SCAN` ceiling);
  `memory.recall` + `rag.retrieve` use it with graceful fallback to the Python loop / lexical.

**To activate live on the server (operational, not code):**
1. Build/pull an **ARM64** sandbox image; set `AGENT_BASH_DOCKER_IMAGE` and **unset
   `AGENT_DISABLE_BASH`** in the server `.env`. (docker-group setup per `docs/SETUP_GUIDE.md`.)
2. Add `GITHUB_TOKEN` to the server `.env` for clone/push/PR.
3. (Optional) add `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` (+ `LANGFUSE_HOST`) and
   `pip install langfuse` to send the span tree to the cloud.
4. Repo mode needs network in the sandbox for clone/installs → set `AGENT_BASH_DOCKER_NETWORK=bridge`.

---

## Features not built
- **Image generation** — code is ready; needs an `image_model:` in `config/models.yaml` + a
  matching provider key.
- **GitHub via MCP (alternative PR path)** — PR creation currently uses the GitHub REST API
  directly (self-contained, no MCP server needed). Wiring a GitHub MCP server into
  `config/mcp.yaml` is an optional alternative if richer GitHub operations are wanted.
- **More connectors** (Slack / DB via MCP) — the adapter (`tools/mcp.py`, `config/mcp.yaml`)
  exists; real servers aren't wired.
- **Browser / computer control** — intentionally skipped.
- **sqlite-vec / FAISS true ANN** — the NumPy index is fast to millions of rows; a real
  sub-linear ANN index is only worth it at much larger scale.

## UI / UX polish
- **Mobile pass** on the new Claude UI (desktop verified; phone drawers need a look).
- **Deep-polish the last two Settings panels** — Health and Schedules (Models/Memory/Fleet done).

## Performance / cost
- Add more **free NVIDIA keys** (`NVIDIA_NIM_API_KEY_1..N`) to multiply throughput.
- **Per-project budgets** + a spend dashboard.
- Prompt caching — deferred (low payoff on NVIDIA's free tier; the classifier cache covers repeats).

## Reliability / quality
- Broaden integration tests further (more edge cases; multi-agent flow tests).

## Security / ops (matters most if ever exposed beyond Tailscale)
- **API rate-limiting** + **encrypt stored API keys** at rest.
- **Off-site backups** (`BACKUP_UPLOAD_CMD`) so backups leave the VM.
- Docker-group membership is root-equivalent — consider rootless Docker for the sandbox.

---

## Suggested next sequence
1. **Activate repo mode + sandbox on the server** (`GITHUB_TOKEN`, flip `AGENT_DISABLE_BASH`
   off, set `AGENT_BASH_DOCKER_IMAGE`/`NETWORK`) and run `scripts/test_repo_mode.py`.
2. **Off-site backups** — set `BACKUP_UPLOAD_CMD` in server `.env`.
3. **Mobile pass** — CSS tweaks for phone drawers.
4. **API rate-limiting** before any wider exposure.
