# AGENT // CORE — End-to-End Test & Fix Report

**Date:** 2026-07-12
**Branch:** `claude/commands-and-lsp`
**Environment:** local (`localhost:8800`, loopback), Docker sandbox `agent-verify:latest`,
paid fleet (DeepSeek + DeepInfra) + free floor (Gemini/NVIDIA NIM).
**Status:** all fixes implemented, validated, and committed (11 commits). Not pushed.

---

## 1. What was done (in order)

1. Ran the dogfood self-engineering harness green (Windows fixes).
2. Brought the app up locally with the Docker sandbox (built `agent-verify:latest`).
3. Ran a **full end-to-end test round** across the whole platform (UI-first, ~13 task
   scenarios + a feature sweep), and verified each run under the hood (fleet telemetry,
   traces, workspace files).
4. Found **11 issues** (3 broken, 4 caveats, plus polish), fixed **all** of them.
5. Re-validated with the full automated suite + a live end-to-end proof of the headline fix.
6. Ran **two real "point it at a repo" tasks** with no hints to observe the whole flow
   (routing → agent → skills → tools → delegation → verify), which surfaced and fixed one
   more skill bug.

---

## 2. Test round — findings (before fixes)

| Area | Result |
|------|--------|
| Chat, explain, coding, multi-file build, frontend+preview | Working |
| Docker sandbox run_bash, prompt cache (79–86%), artifact workbench | Working |
| Run-summary header, changed-files panel, chat grouping, routing editor, Health panel, Model Lab, trace viewer, ⌘K | Working |
| Cost caps, stop, retry, memory recall, checkpoints/rewind | Working |
| **Office doc (.xlsx) generation** | **BROKEN** — no file produced |
| **Human approve/deny card** | **BROKEN** — never appeared |
| **User `/commands` in UI** | **BROKEN** — not surfaced |
| Tier-3 LEAD / delegation | Caveat — never triggered from normal prompts |
| "UNVERIFIED" banner on research; skill over-selection; sub-cent cap display; `/workspace` path guess | Caveats |

Total spend for the whole test round: ~**$0.02**.

---

## 3. Fixes applied and how each was validated

| # | Commit | Fix | Validation |
|---|--------|-----|-----------|
| 1 | `e9fe594` | Bake document libs (openpyxl, python-docx, pptx, reportlab, pypdf…) into the verify Docker image | **Live E2E: agent produced a real `planets.xlsx` (5272 bytes, 9 rows, pandas-readable) in the sandbox, $0.0012** |
| 2 | `52e8c38` | Manager review no longer fail-closes on empty/garbled output; infra-failure falls through to the human card | Unit check: an `[infra]` manager result falls through instead of denying |
| 3 | `06645b1` | Policy matches action rules against commands, not written file content | Unit: `write_file` w/ "deploy" in content → allow; `run_bash git push` → escalate |
| 4 | `8c930c7` | Drop retired NIM ids (`z-ai/glm-5.1` 410, `deepseek-v4-flash` 404) from catalog + chains + tier default | Chains verified 0 dead refs; regression tests updated |
| 5 | `88106b6` | 429 benches a model for 10 min (not re-probed every 60s); sub-cent budget caps display precisely | Full suite green |
| 6 | `a734ddf` | Explicit multi-domain tasks route to the LEAD for delegation | Unit heuristic (positive/negative) + **live cross-domain run routed tier-3 and delegated** |
| 7 | `fb6c50f` | "UNVERIFIED — code not executed" only shows when the agent actually has `run_bash` | Full suite green |
| 8 | `06d38da` | Intent-gate the `web-frontend` skill (stop firing on backend/CLI tasks) | Unit |
| 9 | `bda23d5` | `run_bash` description tells the agent cwd is the workspace + libs are preinstalled | Doc-gen ran clean in 11 iters (was a 15-iter cap failure) |
| 10 | `910d700` | dogfood harness: UTF-8 console output + raw docstring (Windows) | dogfood run green |
| 11 | `f5584a0` | Heavy doc-format skills only auto-load for agents that can run them (found via the real-repo run) | Unit: research → no xlsx; coder → xlsx |

**Note on `/commands`:** it was NOT a code defect — the feature is implemented in source; the
running app was serving a **stale `web/dist`** built before the code landed. Rebuilt the
frontend; `api/commands` is now in the bundle. CI rebuilds on deploy, so the VM would never
have shown this.

### Automated validation (final)
- **260 pytest passed**, 3 skipped
- **170 smoke tests passed**
- **`tsc --noEmit` clean**
- **`npm run build` clean**

---

## 4. Real-repo demonstrations (no hints given)

Seeded an unfamiliar multi-file Python project (`spendtrack`, a real `models/store/core/cli`
architecture with 6 passing tests) and gave real feature requests. The platform decided
routing, agent, and skills entirely on its own.

### Run 1 — "add monthly budgets per category" (single-domain)
Flow captured from the event stream:
```
ROUTE   tier=2 type=coding
ASSIGN  coder (deepseek-v4-flash)
SKILL   [python-project]                (correct; nothing irrelevant pulled)
TOOL    list_files x3, read_file x12     (read the whole codebase first)
TOOL    edit_file x10                    (models -> store -> core -> cli -> tests -> README)
TOOL    run_bash x8 (Docker /ws)         (pytest, fixed a failing test, CLI smoke test)
FALLBACK x3 + RETRY x1                   (DeepSeek errored -> chained to a working model)
```
**Validated output:** budgets implemented across all layers respecting the Store/Tracker
split; **tests 6 → 15, all green**; CLI works end-to-end
(`FOOD  40.00  50.00  -10.00  *** OVER ***`). Cost **$0.0077**, 25 iters.

### Run 2 — "research + implement export + write EXPORT.md, coordinate as steps" (cross-domain)
```
ROUTE   tier=3 type=research   "Multi-step project requiring research, coding, and writing"
PLAN    4 steps: Research -> Implement export -> Write EXPORT.md -> QA   (LEAD master loop)
ASSIGN  research (delegated by lead)
```
**Validated output:** all three deliverables produced — `findings.md` (cited research), the
real `export` command (`Tracker.export()` + argparse), and `EXPORT.md`; test suite passes.
Cost **$0.0141**, 27 iters. This is the proof that the tier-3 LEAD + delegation path
(previously unreachable) now fires on a genuinely multi-part task.

**Bug found + fixed here:** the `xlsx` skill wrongly auto-loaded for the research step and
staged ~1 MB of Office schemas into the workspace — fixed in commit `f5584a0`.

---

## 5. Subsystem scorecard (observed behaviour vs. plan)

| Subsystem | As planned? |
|-----------|-------------|
| Router (tier + task_type) | Yes |
| Dispatcher (agent selection) | Yes |
| Skill selection | Yes (after fixes) |
| Tool loop (read → edit → run) | Yes — reads the repo before editing |
| Docker sandbox execution | Yes |
| Provider fallback + retry | Yes — survived a live provider failure |
| Self-verify / critic gating | Yes |
| LEAD + delegation | Yes — now reachable |
| Security gate (policy + manager + human) | Yes — no spurious escalations |
| Cost / iteration caps | Yes (~$0.008 per real task) |

---

## 6. Known rough edges (not blockers)

- **Research subagent fell to a weak free model** (`qwen3.5-122b`) when the paid Nemotron was
  rate-limited, and emitted one garbled tool call. Model-quality issue, not a code bug.
- **Coder still guesses `/workspace` once** before `/ws` despite the description hint;
  self-corrects immediately (1 wasted call).
- **Delegation was shallow** — the LEAD delegated the research step but did the coding/doc
  itself. Works, but not full fan-out.
- **Flaky smoke test:** the memory `_facts[0]` assertion can `IndexError` when a free model
  returns no extracted facts. Cosmetic test fragility.
- **Gemini free daily quota is exhausted** right now (16/17 calls 429). The fallback chain
  handles it, but it adds latency; the 429-cooldown fix reduces the re-probe waste.

---

## 7. Next steps

**To ship this work**
1. Push `claude/commands-and-lsp` and merge to `main` (auto-deploys via the VM runner).
2. On the VM after deploy: ensure `DEEPSEEK_API_KEY` + `DEEPINFRA_API_KEY` are in the server
   `.env`; **rebuild `agent-verify:latest`** (now includes the doc libs) via
   `docker/build-verify-image.sh`; set `AGENT_DAILY_USD_CAP` (~$2–3).

**Verification still owed (blocked this session by a broken browser-preview pane)**
3. Live-UI re-confirm the three previously-broken items in the actual app: the **human
   Approve/Deny card** now appears, the **`/commands` menu**, and **doc generation** — all are
   covered by unit/component/E2E evidence but weren't re-driven through the live UI.

**Optional hardening / follow-ups**
4. Force `run_bash` cwd awareness harder (inject the sandbox path into the system prompt) to
   kill the `/workspace` guess entirely.
5. Reconsider the research free-floor order so the research subagent doesn't fall to a weak
   tool-caller under rate limits.
6. Harden the flaky smoke memory assertion.
7. Run `python -m evals` (A/B) once comfortable, and a deeper delegation fan-out test.

**Housekeeping**
8. At session end: update `HANDOFF.md` (current state + next tasks) and optionally commit
   this report. The local `AGENTS.md` / news-agents files remain intentionally uncommitted.
