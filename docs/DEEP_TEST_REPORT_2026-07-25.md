# Deep-Test — Final Round (2026-07-25)

**Question this round answers:** *Can I rely on Nikki for real projects?*
**Headline: 34/34 external checks pass** (33/34 on the live campaign; the one gap — the
code-review rubric not reaching a review that routed to `coder` — was fixed mid-round and
re-verified green). Every check is externally verified (real pytest exit codes, recomputed
balances, independent RBAC probes, DOM/file checks) — never the agent's own say-so.

This round used a **fresh server on the current code** (all four new skills active) and threw
**genuinely different, harder tasks** at it than last time — including a hard build it had never
seen.

---

## The short answer on reliability

**Yes — as a supervised power-tool for real projects, today.** The trust-critical behaviours hold:
it verifies its own work against **real** test runs (and flags UNVERIFIED honestly instead of
lying when it can't), it isolates memory across projects, it resists prompt-injection from files,
and the security gate stops irreversible actions pending human approval.

**Not yet for fully-unattended, irreversible production automation.** The hardest from-scratch
builds still ride on model quality — it *succeeded* on a brand-new complex app this round, but any
single run can miss; the safety net is that it tells you when it isn't sure. See the honest limits
at the end.

---

## What was different / harder this round

| Test | Why it's a real probe | Result |
|---|---|---|
| **Expense-splitter** (new hard build, *not* the Kanban) | From scratch: money-math with exact cent-rounding, balances that must sum to zero, settlement, RBAC, isolation, UI — a domain it was never tuned on | **Built + green.** Own suite `11 passed`; independent probe confirmed balances-sum-zero + 7 forbidden-access (403) assertions; app+UI+tests all present |
| **Secure-coding** (does `security-guidance` change the code?) | Builds auth + SQL search; code externally scanned for injection & plaintext passwords | **Parameterized SQL, hashed passwords**, suite green; skill confirmed firing |
| **Frontend-design** (does the aesthetic skill work?) | Builds a landing page; palette/typography inspected | **Subject-grounded** palette + real type scale + signature element; skill firing |
| **Code-review rubric** | Plants a real overdraft bug in `bank.py` | **Real bug caught**, prioritized; rubric applied (after the fix below) |

## Full scorecard (this round)

| Aspect | Checks | Score | Note |
|---|---|---|---|
| Task competence | 7/7 | **9/10** | simple → medium fix-in-place → a new hard multi-file app, all delivered & green |
| Self-verification | 5/5* | **9/10** | ran its own tests; self-corrected the medium to green; hard build passed an *independent* probe |
| Security (gate + secure-coding + injection) | 5/5 | **9/10** | boundaries held; ignored planted README instructions; wrote parameterized SQL + hashed passwords |
| Permission modes | 6/6 | **9/10** | auto & careful raised approval cards on an irreversible action; trusted auto-approved |
| Memory | 3/3 | **9/10** | shared within a project, **no leak** to an unrelated chat, `/todo` works |
| Model routing | info | **8/10** | secure task escalated to a planned (architect+coder) build; hard task ran at high effort |
| Frontend design *(new)* | info | **8/10** | considered, on-theme design; mild lean to a warm-cream palette — taste still wants a human eye |
| Mid-run steering | 1/1 | **8/10** | a "add a search box" instruction folded into a live run and shipped |
| Task understanding | 2/2 | **8/10** | picked up a vague ("track my workouts") and a garbled, typo-ridden brief |
| Reliability (checkpoint / scheduling / connector) | 5/5 | **9/10** | rewind restored; scheduled job ran to done; GitHub MCP tools called live |

*\*Self-verification was 4/5 on the raw campaign; the miss was a measurement/reachability gap (below), fixed and re-verified to 5/5.*

**Overall: ~8.2 → ~8.8 / 10.**

## Optimizations found and applied this round

1. **Code-review rubric wasn't reaching reviews** — a "review this file" task routes to `coder`
   (the dispatcher sends review work there more than to `code-reviewer`), and the rubric was
   granted only to `code-reviewer`/`critic`, so it never applied. **Fixed:** broadened the grant to
   `coder`/`fast-coder` (it's keyword-gated to review/audit/PR tasks, so it stays inert on normal
   builds). Re-verified live — rubric now fires and the real bug is still caught. *(commit b2a36c9)*
2. **Harness couldn't see which skills fired** — the telemetry read the wrong event key (`name`
   instead of the `skills` list), so it always reported `[]`, masking that the new skills were
   working. **Fixed** — now correctly shows `security-guidance`, `web-frontend`, `code-review`
   firing on the right tasks. *(commit e577f19)*

## Honest limits (what "8.8 not 10" means)

- **Hardest from-scratch builds are model-bound.** It nailed the expense-splitter, but a 10/10
  guarantee on every hard build is impossible for any LLM tool. The real safeguard is the
  **done-gate**: it runs the actual tests and reports *verified-green* or *honestly UNVERIFIED* —
  it does not fake success.
- **Visual taste needs a human glance.** The design skill lifts output well above generic, but a
  machine can't score aesthetics; give any client-facing UI a 5-minute look.
- **A few features were proven once, not exhaustively** (e.g. mid-run steering) — reliable in
  testing, but not battle-hardened across thousands of runs.
- **Keep a human in the loop for irreversible actions.** Run in `auto`/`careful` mode, review
  diffs, and let it run tests. That's the intended operating posture — and in it, it's dependable.

## How to use it on real projects now
Point it at a repo, keep approvals on, let it build-and-test in small verified steps, and trust
its green/UNVERIFIED verdict over its prose. Good fit today: small-to-medium multi-file apps,
bug-fixing in place, tests, research, data analysis, UI prototypes. Hold back on: unattended
production ops with irreversible side effects.
