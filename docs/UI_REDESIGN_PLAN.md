# UI REDESIGN PLAN — modern-minimal refactor (single source of truth)

_Created 2026-06-14. **Supersedes `docs/UI_STRUCTURE_PLAN.md`** (the 2026-06-07 warm-paper plan),
which was implemented but has since drifted (Settings grew from 5 tabs to 9). This is the
corrected, authoritative structure. Decision locked: **modern-minimal look (Claude/ChatGPT
style)**, plan-first (Stitch-vs-code decided after this doc)._

---

## 0. The diagnosis (why it feels "all over the place")

Looked at the live code. The **shell is actually fine** — three frames (sidebar · centered
chat · contextual right panel), mobile drawers, a slim top bar. The problems are:

1. **Settings ballooned 5 → 9 tabs** (General, Limits, Models, Fleet & keys, Model health,
   Schedules, Roadmap, Memory, Security). Features got bolted on without regrouping. *This is
   the single biggest source of the "cluttered" feeling.*
2. **No real visual hierarchy** — everything is the same weight, 1px borders everywhere, the
   chat column stretches full-width so reading feels noisy.
3. **Missing the calm-defaults** the old plan promised but never got built: no welcome/empty
   state, the command palette (⌘K) only makes a new chat, no toasts, no end-of-run summary.
4. **A dev artifact leaked into the product** — the "Roadmap" tab is project status, not user
   config; it doesn't belong in the running app.

The fix is **not** a new theme slapped on top — it's: regroup Settings, give the content real
hierarchy, switch to a clean neutral aesthetic, and finally build the calm-defaults.

---

## 1. The new look — modern minimal (Claude / ChatGPT)

Drop "warm paper everywhere." Move to **clean neutral surfaces + one restrained accent +
generous whitespace + content-first**. (We keep a single muted clay accent — it echoes Claude
and your existing brand — but used *sparingly*, only for primary actions and active states.)

### Design tokens (paste-ready — these replace the current Tailwind theme)

| Token | Light | Dark | Use |
|---|---|---|---|
| `bg` (canvas) | `#FFFFFF` | `#1A1A1A` | main chat area |
| `surface` (raised) | `#F7F7F8` | `#242424` | sidebar, cards, composer |
| `surface-2` | `#F0F0F2` | `#2E2E2E` | hover, nested rows |
| `border` (hairline) | `#ECECEC` | `#333333` | use *sparingly* — prefer surface contrast over lines |
| `text` | `#1F1F1F` | `#ECECEC` | body |
| `muted` | `#6E6E80` | `#9A9A9A` | labels, hints, timestamps |
| `accent` | `#C8674F` | `#D4795F` | **only** primary buttons + active state |
| `accent-soft` | `#F6E9E4` | `#3A2A24` | active-tab background, selected chat |

### Type & spacing
- **One sans for everything:** Inter or Geist (UI + body). **JetBrains Mono** for code.
  *Drop the serif headings* — serif reads "dated" in a minimal tool. (Optional exception: a
  serif **only** on the welcome-screen hero, nowhere else.)
- Body text **15–16px** (bump up from the current tiny 11px labels — that smallness is part of
  the "busy" feel). Section labels 11px uppercase tracked, used rarely.
- **Radius:** 12px cards, 8px controls. **Shadows:** almost none — separate with surface color,
  not borders + shadows stacked.
- **The chat column gets a max reading width (~720px), centered** — like ChatGPT/Claude. Today
  it stretches edge-to-edge, which is the noisiest part.

---

## 2. The shell (keep — refine visually)

```
┌────────────┬───────────────────────────────────┬──────────────┐
│  SIDEBAR   │  TOP BAR (status · cost · gear)    │  RIGHT PANEL │
│            ├───────────────────────────────────┤  (contextual,│
│ projects   │                                   │   collapsed  │
│ + new chat │      CHAT THREAD (centered,        │   by default)│
│ + search   │      max-width ~720px)            │              │
│ + list     │                                   │  Files       │
│            │                                   │  Rewind      │
│            │  ┌─────────────────────────────┐  │  Skills      │
│            │  │ Activity strip (collapsible)│  │  Tasks       │
│            │  ├─────────────────────────────┤  │              │
│            │  │ COMPOSER (textarea·⚙·attach·│  │              │
│            │  │           send)             │  │              │
│            │  └─────────────────────────────┘  │              │
└────────────┴───────────────────────────────────┴──────────────┘
```

- **Top bar (already slim — keep):** left = status pill (`● Backend Live` / `● Working` pulse /
  `● Offline`); right = live **Run cost** + **Settings** gear. Make it quieter (smaller, muted).
- **Sidebar:** Projects selector · **New chat** · search · chat list (hover → star/rename/delete).
  Selected chat uses `accent-soft`, not a heavy fill.

---

## 3. Every current feature → its home (the full map)

This is the complete inventory from the live components, so nothing is lost.

### Stays on the main screen
| Feature | Home | Component |
|---|---|---|
| Type / attach / send-stop | **Composer** (minimal) | `Composer.tsx` |
| Per-run tweaks (mode, plan-first, force-QA, parallel, stream, max $/loops, queue-as-job) | **Run-options popover** (⚙ in composer) | `Composer.tsx` |
| Chat thread, messages, code/diagram render | **Center** | `Chat.tsx`, `CodeBlock.tsx`, `Mermaid.tsx` |
| New chat · search · chat list · projects | **Sidebar** | `Sidebar.tsx`, `ProjectModal.tsx` |
| Status · run cost · settings | **Top bar** | `App.tsx` |

### Right panel — 4 contextual sections (keep; fix the behavior)
| Section | Shows when | Component |
|---|---|---|
| **Files / Artifacts** (primary) | a file is created → **auto-expands the first time** | `FilesPanel.tsx` |
| **Rewind** (checkpoints) | a checkpoint exists | `CheckpointsPanel.tsx` |
| **Skills** (which applied) | a skill was used | `SkillsPanel.tsx` |
| **Tasks** (background jobs) | a job is queued/running (badge) | `JobsPanel.tsx` |

Behavior to enforce: collapsed rail with badges by default; empty sections hidden; auto-expand
on first artifact. (If that's not happening today, it's the implementation fix.)

### Settings — **9 tabs → 5** (the core cleanup)
| New tab | Absorbs (old tabs/locations) | Component(s) |
|---|---|---|
| **1. General** | theme · default approval mode · export chat | `SettingsModal.tsx` |
| **2. Limits & cost** | default max $/loops · daily cap · spent today | `SettingsModal.tsx` |
| **3. Models & keys** | tier models · cost-first/fixed strategy · model scout · **Fleet & keys** · **Model health** (as a sub-section) · link to **Model Lab** | `ModelRail.tsx` + `FleetPanel.tsx` + `HealthPanel.tsx` + `BenchmarkModal.tsx` |
| **4. Memory** | remembered facts (add/forget) · proposed rules (approve/reject) | `MemoryPanel.tsx` |
| **5. Advanced** | access token (Security) · **Schedules** · any future power-user knobs | `SettingsModal.tsx` + `SchedulesPanel.tsx` |

**Removed from the app entirely:** the **Roadmap** tab (`RoadmapPanel.tsx`) — it's project
status, it belongs in `STATUS.md`/`HANDOFF.md`, not the running product. (Leave the component
in the repo if you like, just unmount it.)

> Result: Settings goes from a 9-tab wall to **5 clear homes**, and "everything about models"
> (tiers, keys, health, lab) finally lives in one place instead of three.

### Lives inline in the conversation (contextual)
| Feature | Behavior |
|---|---|
| Activity strip (route → agent → tool → QA) | one collapsible line above the composer; **collapsed by default** for simple chats |
| Approval card ("Agent wants to run `bash …`") | inline card, Approve/Deny, risk-colored |
| Plan-first preview | inline "here's the plan — Approve to run" |
| 👍/👎 · copy · edit-and-branch · regenerate | on message hover |

---

## 4. What to ADD (the calm-defaults that were promised but never built)

1. **Welcome / empty state** — centered greeting + 3–4 example chips ("Research a topic", "Write
   & run a script", "Make a spreadsheet", "Summarize a file"). Kills the blank-page feel. *(The
   only place a serif hero font is allowed.)*
2. **Real command palette (⌘/Ctrl-K)** — today it only makes a new chat. Upgrade to: jump to a
   chat, swap a model, open Settings, run Model Lab. This is *how* power features stay reachable
   without cluttering the screen.
3. **Toasts** — "budget cap hit", "run stopped", "error — retry?" — instead of stuffing these
   into the message thread.
4. **End-of-run summary chip** — "Done · tier-2 · 5 steps · $0.0035" under the final answer.

---

## 5. Done-right checklist
- [ ] A first-time user sees only: chat history, a welcome prompt + example chips, the composer.
- [ ] The chat column is centered with a comfortable reading width — not full-bleed.
- [ ] Settings is **5 tabs**, every model-related thing in one of them.
- [ ] No "Roadmap" tab in the running app.
- [ ] Right panel is collapsed/empty until the agent produces something; auto-expands on first file.
- [ ] One restrained accent color; whitespace and surface contrast do the work, not borders.
- [ ] Command palette, toasts, empty state, and run-summary chip all exist.

---

## 6. Scope & safety (when we build it)
**This is a frontend-only change — no backend, no API, no event-contract changes.** Every flag
and data source already lives in the Zustand store (`web/src/lib/store.ts`: `mode`, `planFirst`,
`review`, `parallel`, `stream`, `maxUsd`, `maxIter`, `strategy`, `spend`, `theme`, token, plus
`files/checkpoints/skills/jobs/facts/rules`). The work is layout + grouping + theme + the four
new calm-defaults.

**Components touched:** `tailwind.config` (new tokens) · `App.tsx` (shell polish) · `Chat.tsx`
(centered column, empty state, run-summary chip) · `Composer.tsx` (visual refine) ·
`SettingsModal.tsx` (9→5 tabs, absorb Fleet/Health/Schedules, drop Roadmap) · `RightPanel.tsx`
(enforce contextual collapse) · **new:** a `CommandPalette.tsx` + a `Toast` system + a
`WelcomeState`.

---

## 7. Next decision (you said "decide tooling after")
Now that the structure is fixed, pick how to execute:
- **A) Stitch first** — I turn Section 1 (tokens) + Section 3 (the real feature map) into a
  paste-ready Stitch prompt; you generate screens, send the ones you like, I rebuild to match.
  Best when you want to *see and choose* the look before committing.
- **B) Code directly** — I apply this plan straight in the repo (new theme tokens, regroup
  Settings, build the calm-defaults), you review it running and we iterate. Faster, no round-trip.

Either way the structure above is the contract.
