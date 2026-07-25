# Plugin Evaluation — should Nikki borrow from 6 Claude Code plugins?

**Date:** 2026-07-25

> **Update (2026-07-25) — the shortlist was implemented.** Four items landed as skills (zero
> edits to the protected `config/agents.yaml`): the **frontend-design** aesthetic method folded
> into [`skills/web-frontend/SKILL.md`](../skills/web-frontend/SKILL.md); new
> [`skills/security-guidance/`](../skills/security-guidance/SKILL.md),
> [`skills/code-review/`](../skills/code-review/SKILL.md), and
> [`skills/verification-before-completion/`](../skills/verification-before-completion/SKILL.md)
> (the additive superpowers pick — `systematic-debugging` was already covered by `skills/debugging`).
> The skill risk-scanner ([`core/skill_scan.py`](../core/skill_scan.py)) was made frontmatter-aware
> and avoidance-cue-aware so a secure-coding skill that *names* dangerous patterns isn't false-flagged.
> **claude-mem skipped** as recommended. Full suite green (415 passed); +10 new tests. The
> everything-below is the original evaluation that drove these choices.

## The one thing to understand first

These six things are **Claude Code plugins** — built to extend *Claude Code* (the coding
assistant). Nikki is a **separate product** that happens to be *built with* Claude Code. So the
real question isn't "install the plugin" — it's **"is the idea inside the plugin worth baking into
Nikki's own agents so Nikki's output gets better?"**

That question has a lucky answer: **Nikki already has the machinery to absorb the good parts as
plain skills, with no engine surgery.** Specifically Nikki already ships:

- A **skills host** ([`core/skills.py`](../core/skills.py)) that reads Anthropic-format `SKILL.md`
  folders, injects them only when relevant, security-scans them, and can enable/disable each one.
  New skills arrive **disabled until a human approves** — so nothing unvetted can steer a task.
- A **4-type scoped memory** ([`server/memory.py`](../server/memory.py)) — working, episodic,
  semantic, procedural — isolated per project/session so memories don't leak between chats.
- A **4-layer runtime security gate** ([`core/policy.py`](../core/policy.py) +
  [`server/approvals.py`](../server/approvals.py)) that blocks or human-gates risky actions.

So every plugin below is scored against **what Nikki already does** — is it *redundant*, *partial*,
or genuinely *additive*?

## Licensing (this decides *how* we borrow, not *whether*)

| Plugin | License | What that means for us |
|---|---|---|
| superpowers | **MIT** | Copy the markdown freely. |
| claude-mem | **Apache-2.0** | Copy freely. |
| frontend-design, code-review, security-guidance | **Proprietary** (© Anthropic, all rights reserved) | **Do not paste their text.** Re-author the *ideas* in our own words. The design principles and the security vuln-patterns are public, common knowledge — re-expressing them is fine; copying their exact prose is not. |

---

## Plugin-by-plugin verdict

### 1. superpowers (obra / Jesse Vincent) — a "skills + methodology" framework
**What it is:** a big library of markdown skills that force a disciplined pipeline —
brainstorm → write a plan → dispatch subagents → **verify before calling it done** → code review —
plus Claude-Code-only plumbing (session hooks, a plugin marketplace).

**Fit to Nikki:** Nikki *already implements this methodology in its engine* — the plan-first
orchestrator, the `delegate` sub-agent mechanism, the deterministic "did the tests actually pass"
done-gate, and the critic/QA pass. The hooks and marketplace don't apply to Nikki at all.

- **Pros:** MIT (safe to copy); a few individual skill write-ups are excellent standalone prose.
- **Cons:** ~80% duplicates what Nikki's orchestrator already does; the auto-activation magic is
  Claude-Code-only and won't come along.

> **Verdict: LOW — cherry-pick, don't adopt.** Optionally drop 1–3 skill bodies straight into
> `skills/` (e.g. `systematic-debugging`, `verification-before-completion`, `writing-plans`) as
> extra guidance. It is **not** a framework to adopt — Nikki *is* the framework.

### 2. claude-mem (thedotmack) — persistent memory across sessions
**What it is:** it captures a session, compresses it into summaries at session-end, stores it in
SQLite + a vector DB, and re-injects relevant history next time. **All of it is driven by Claude
Code's session hooks** (`SessionStart` / `PostToolUse` / `SessionEnd`).

**Fit to Nikki:** Nikki's memory is **more capable, not less** — four typed stores, hard
project/session/global scope isolation (the anti-leak guarantee), human-gated "rules," and both
embedding and offline-lexical recall. Session-end compression already exists (`/compact` +
rolling summaries).

- **Pros:** none that Nikki lacks.
- **Cons:** its automation is welded to Claude-Code hooks Nikki doesn't have; adopting it would be
  a **downgrade** and a rebuild.

> **Verdict: SKIP.** Nikki already does memory better. Nothing to borrow.

### 3. frontend-design (Anthropic) — UI *taste*, as pure guidance
**What it is:** a `SKILL.md` of design principles — avoid the three generic "AI-looking" aesthetics,
treat **typography as identity**, run a **two-pass process** (write a short design plan, critique it
for uniqueness, *then* build), concentrate boldness in **one signature element**, use motion with
purpose.

**Fit to Nikki:** Nikki's [`skills/web-frontend/SKILL.md`](../skills/web-frontend/SKILL.md) only
enforces "clean, accessible, and it actually works" — there is **no opinionated aesthetic method**.
This is the clearest *overlap-but-shallow* gap, and it maps exactly onto the weakest axis from the
deep-test report (visual UX).

- **Pros:** provider-agnostic prose; drops into Nikki's skills host with **zero engine change**; the
  single biggest lever on *visible* output quality.
- **Cons:** proprietary → re-author in our words; it raises the bar but can't *guarantee* taste.

> **Verdict: WORTH IT — top pick.** Re-author an aesthetic method into `web-frontend` (or a new
> `frontend-design` skill). Low effort, high and immediately visible payoff.

### 4. code-review (Anthropic) — a structured review command
**What it is:** it fans out redundant parallel reviewers, runs a **separate validation pass to kill
false positives**, scores each finding **0–100 and drops anything under 80**, and flags **only
high-signal issues** (real compile/logic/guideline breaks — never style nits).

**Fit to Nikki:** Nikki already has a `critic` + a `code-reviewer` agent + a **real** test-based
done-gate (running the actual test suite is arguably stronger than an LLM confidence score). What's
*missing* is a **formal rubric** — today Nikki's review criteria are prose scattered across two
agent prompts.

- **Pros:** the "high-signal-only + confidence threshold + re-verify each finding" recipe would
  formalize the critic and cut false alarms.
- **Cons:** the GitHub-PR / CLAUDE.md-file machinery is Claude-Code-only and irrelevant to Nikki.

> **Verdict: PARTIAL — worth it, lightweight.** Fold the high-signal-only rubric + a confidence
> threshold (and optionally a per-finding re-verify pass) into the `code-reviewer` prompt. No new
> engine code.

### 5. security-guidance (Anthropic) — advisory secure-coding
**What it is:** layered defensive security — a ~25-rule **vulnerability pattern catalog** (`eval`,
`pickle.load`, unsafe `yaml.load`, `.innerHTML=`, TLS `verify=False`, AES-ECB, XXE, …), plus a
fast-model diff review and an agentic commit review, plus tiered custom-policy markdown.

**Fit to Nikki:** Nikki has a strong runtime **enforcement** gate, but it **injects no advisory
secure-coding guidance into the agents that write code.** So this is **genuinely additive** — it
does *not* overlap the runtime gate; it teaches the builders to write safer code in the first place.

- **Pros:** the vuln patterns are public secure-coding knowledge (safe to re-express); a natural fit
  for a security-conscious product; two clean forms — (a) a `security-guidance` `SKILL.md` for the
  coder/frontend agents, and optionally (b) a small static regex scan before write/commit that
  complements the policy gate.
- **Cons:** the plugin's Python `hooks/` runtime is Claude-Code-bound — don't port it; re-author the
  catalog only.

> **Verdict: WORTH IT.** Advisory, build-time security guidance is a real missing layer for Nikki.

### 6. anthropics/claude-code (the repo itself)
Not a plugin — it's the **home** of #3–#5. Nothing to integrate on its own.

---

## Scorecard

| Plugin | License | Overlaps what Nikki has | Additive? | Effort | Verdict |
|---|---|---|---|---|---|
| **frontend-design** | proprietary | `web-frontend` skill (shallow) | **Yes** | Low | **Do — top pick** |
| **security-guidance** | proprietary | runtime gate only (no advice) | **Yes** | Low–Med | **Do** |
| **code-review** | proprietary | critic + done-gate | Partial | Low | Do (rubric only) |
| superpowers | MIT | orchestrator + skills host | Small | Low | Cherry-pick 1–3 skills |
| claude-mem | Apache-2 | memory (Nikki is richer) | No | — | **Skip** |
| claude-code (repo) | proprietary | — | — | — | N/A (umbrella) |

## Recommended integration roadmap (for a *later* pass — not done yet)

Ranked by payoff-per-effort. Every item lands as a **skill or a prompt tweak**, not engine surgery;
each new skill is auto-scanned and arrives **disabled until you enable it**, so nothing steers a
task without your review.

1. **frontend-design skill** — biggest visible win; re-author an aesthetic method into `web-frontend`.
2. **security-guidance skill** — re-author the ~25 vuln patterns as build-time guidance for the coder
   agent; optionally add a tiny pre-write regex scan later.
3. **code-review rubric** — fold the high-signal + confidence-threshold recipe into `code-reviewer`.
4. **superpowers cherry-picks (optional)** — drop 1–3 MIT skill bodies into `skills/`.
5. **claude-mem — skip.**

## What this pass did *not* touch
No change to `skills/`, `config/`, `core/`, `server/`, and the news/feeds WIP is untouched. This is
a decision document; implementation happens only when you say go.
