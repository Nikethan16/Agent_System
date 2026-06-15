# BACKLOG — what's left to do

_Last updated: 2026-06-14. The prioritized list of remaining work. Nothing here is blocking —
the app is complete and deployed live. Items are roughly ordered by value. See `HANDOFF.md`
for current state and `STATUS.md` for what's already done._

---

## ⭐ #1 — "Work on a repo" mode (Claude-Code-style)  — NOT BUILT
The biggest missing capability. Goal: point the agent at a real codebase → it **clones +
understands it first** → you ask for a refactor/fix/optimization → it edits the actual repo and
can push the change back as a PR.

**What already exists:** the coder agent does explore → read → `edit_file` (surgical) → run →
verify, sandboxed to a per-chat workspace. The *editing engine* is there.

**What's missing (the glue):**
1. **Load a repo** — UI action: paste a GitHub URL (or local path) → `git clone` into the
   session workspace. Needs a scoped GitHub token.
2. **"Understand first" pass** — a dedicated repo-mapping step (structure, key files,
   conventions → a summary the agents read before changing anything); persist as project
   knowledge / RAG.
3. **Push back out** — branch / commit / open a PR (gh or GitHub API), gated by approval.
4. **Safety prerequisite** — run shell inside the **Docker sandbox** (`AGENT_BASH_DOCKER_IMAGE`)
   so clone/build/run can't touch the host. Currently `AGENT_DISABLE_BASH=1` on the server.

Pairs naturally with turning on the Docker shell sandbox (below).

---

## Features not built
- **Image generation** — code is ready; needs an `image_model:` in `config/models.yaml` + a
  matching provider key.
- **Real ANN vector index** for memory/RAG — today embeddings are scored per-row (fine until
  thousands of memories); a proper index speeds recall at scale.
- **More connectors** (GitHub / Slack / DB via MCP) — the adapter (`tools/mcp.py`,
  `config/mcp.yaml`) exists; real servers aren't wired.
- **Cloud tracing (Langfuse)** — local JSONL traces work; cloud needs `LANGFUSE_*` keys + finishing
  the forward stub in `server/trace.py`.
- **Browser / computer control** — intentionally skipped.

## UI / UX polish
- **File `+/- line counts`** in the run summary (currently shows file names + tool count; line
  counts need diff computation per run).
- **Deep-polish the last two Settings panels** — Health and Schedules (Models/Memory/Fleet done
  2026-06-14).
- **Mobile pass** on the new Claude UI (desktop verified; phone drawers need a look).
- Stream the **lead's final answer**; smarter activity-strip defaults.
- Cleanups: remove the now-unused `web/src/components/RoadmapPanel.tsx`; optional one-click
  "clear old chats" (the local test chats — direct / boot test / Renamed — are harmless leftovers).

## Performance / cost
- Add more **free NVIDIA keys** (`NVIDIA_NIM_API_KEY_1..N`) to multiply throughput.
- **Per-project budgets** + a spend dashboard.
- Prompt caching — deferred (low payoff on NVIDIA's free tier; the classifier cache covers repeats).

## Reliability / quality
- Broaden tests beyond the 158-check smoke (real integration tests).
- Apply the **untrusted-content wrapper** to *all* content sources, not just fetched web pages.

## Security / ops (matters most if ever exposed beyond Tailscale)
- **Turn on the Docker shell sandbox** (`AGENT_BASH_DOCKER_IMAGE`) — also a prerequisite for repo mode.
- **API rate-limiting** + **encrypt stored API keys** at rest.
- **Off-site backups** (`BACKUP_UPLOAD_CMD`) so backups leave the VM.

---

## Suggested next sequence
1. **Docker shell sandbox** on the server (small; unlocks safe shell + repo mode).
2. **Repo mode** (load → understand → edit → PR) — the marquee capability.
3. Quick UI wins (file +/- counts, Health/Schedules polish, mobile pass).
