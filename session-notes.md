# Session notes — handoff

_Start a session with: "Read session-notes.md and continue from there."_

## 2026-06-15 — repo mode + Docker sandbox + tracing + ANN index

**Did:** Shipped 4 backlog items on branch `claude/serene-lamport-r1ix0k` (commit `513eb24`,
pushed; 158/158 smoke). (1) "Work on a repo" mode — `tools/github.py`, `repo-engineer` agent,
`repo` playbook. (2) Docker sandbox hardened — `core/tools.py` fails closed without an image;
`run_bash` → RISK_WRITE when sandboxed. (3) Langfuse span-tree tracing — `server/trace.py`
rewrite + offline callback hook in `core/llm.py`. (4) NumPy ANN index — `server/vectorstore.py`.

**Decisions:** Bash approvals relaxed to RISK_WRITE when Docker is configured. Repo content =
untrusted DATA. **Deviation to confirm:** PR creation uses GitHub REST API (self-contained),
not the originally-agreed MCP path — flag for owner.

**Next steps:** (1) Activate on server `.env`: ARM64 sandbox image + unset `AGENT_DISABLE_BASH`,
add `GITHUB_TOKEN`, optional `LANGFUSE_*`. (2) End-to-end repo-mode test. (3) Trace-viewer UI +
deferred UI polish (file +/- counts, mobile, Health/Schedules).
