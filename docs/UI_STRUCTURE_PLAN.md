# AGENT // CORE — UI Structure Plan (declutter → Stitch-ready)

_Last updated: 2026-06-07. A complete, plain-language plan for restructuring the web UI so
it stops showing every control at once. Goes through **every** feature, decides **where it
lives**, flags **what to add** and **what to remove**, and ends with a **paste-into-Stitch
prompt**. The visual style (warm paper + terracotta, Source Serif / Geist / JetBrains Mono,
rounded cards, light+dark) stays — only the **structure** changes. (Implemented 2026-06-07;
this superseded an earlier UI brief.)_

---

## 1. The problem (why it feels cluttered)

Right now the main screen shows **everything, always** — even for a one-word "hi":
- The **composer** carries 8+ controls inline: approval mode (auto/careful/trusted), Plan-First,
  Force QA, Parallel, Stream, a `$` budget box, a `loops` box, attach, queue-as-job, send.
- The **right panel** always shows **6 tabs** (Files, Rewind, Memory, Skills, Tasks, Models),
  most of them empty most of the time.
- The **top bar** mixes an everyday action (Export) with a power tool (Bench / Model Lab).
- Several controls live in **two places** (approval mode + budgets are in the composer *and*
  Settings) — so it's unclear which one matters.

**The fix is one idea: progressive disclosure.** Show the 20% used 80% of the time; put the
rest one click away. A first-timer should see only: their chats, a text box, and Send.

---

## 2. The new structure — four homes for everything

Every feature belongs to exactly **one** of four places:

| Home | What it holds | When it shows |
|---|---|---|
| **A. Composer** (the box) | type a task · attach · **Run options** button · send/stop | always (minimal) |
| **B. Run-options popover** | per-**this-run** tweaks: approval mode, plan-first, force QA, parallel, stream, max $/loops | only when you click the sliders icon |
| **C. Right panel** (contextual) | per-chat **output**: Files, Rewind, Skills, Tasks | only when there's something to show |
| **D. Settings** (modal) | global **config**: theme, defaults, daily cap, models, memory, token, Model Lab | only when you open it |

Plus the two frames that stay simple: a **slim top bar** (status · run cost · settings) and the
**left sidebar** (chats: new, search, list, star, rename, delete, projects).

> Rule of thumb: **per-chat output → right panel · per-run tweak → popover · global config →
> Settings · the one thing you do every time (type & send) → composer.**

---

## 3. Every feature → where it goes (the full map)

This is the complete inventory pulled from the live code, so nothing is missed.

### Stays on the main screen (the essential 20%)
| Feature | Home | Notes |
|---|---|---|
| Type a task | **Composer** | the single focus |
| Attach a file | **Composer** | small icon |
| Send / Stop | **Composer** | the only filled terracotta button at rest |
| New chat, search, chat list | **Sidebar** | keep; rename/star/delete on hover |
| Projects (switch/create) | **Sidebar** | a selector at the top of the list |
| Connection status · Run cost | **Top bar** | status pill + live $ |
| Settings | **Top bar** | a gear, far right |

### Moves into the Run-options popover (per-run, opened from the composer)
| Feature | Was | Why move it |
|---|---|---|
| Approval mode (auto/careful/trusted) | composer | rarely changed per message; default lives in Settings |
| Plan-first | composer | occasional |
| Force QA | composer | QA already runs automatically — this is a rare override |
| Parallel subtasks | composer | advanced |
| Stream tokens | composer | on by default; rarely toggled |
| Max $ / Max loops (this run) | composer | pre-filled from Settings; edit affects this run only |
| Queue as background task | composer | move to the popover or a `···` action — niche |

### Moves into Settings (global configuration, not per-chat)
| Feature | Was | Why move it |
|---|---|---|
| Default approval mode | composer + Settings | one home for the default |
| Default Max $ / loops | composer + Settings | one home for the default |
| Daily spend cap · spent today | Settings | keep |
| Theme (light/dark) | sidebar/settings | keep in Settings (one switch) |
| Models: tiers, swap, strategy (cost-first/fixed) | right-panel tab | it's configuration, not per-chat |
| Model scout (discover models) | models tab | under Settings → Models |
| **Model Lab / Bench** | **top bar** | a power tool → Settings → Advanced (or command palette) |
| Memory: facts (view/add/forget) | right-panel tab | config-like → Settings → Memory |
| Memory: rules (approve/reject) | right-panel tab | config-like → Settings → Memory |
| Access token | Settings | keep; label "only needed when hosting off this machine" |
| Agent roster (read-only list) | (hidden) | optional: Settings → About/Team |

### Moves into the chat overflow menu (`···` on the conversation)
| Feature | Was |
|---|---|
| Export chat (markdown) | top bar |
| Regenerate last answer | (per-message) — keep on hover too |
| Rename / delete this chat | sidebar hover — also here |

### Stays in the right panel, but contextual (appears only when it has content)
| Section | Shows when |
|---|---|
| **Files / Artifacts** (primary) | the agent creates a file — **auto-opens the panel the first time** |
| **Rewind** (checkpoints) | a checkpoint exists |
| **Skills** (which applied) | a skill was used (read-mostly) |
| **Tasks** (background jobs) | a job is queued/running — show a badge |

### Lives in the conversation thread (inline, contextual)
| Feature | Behavior |
|---|---|
| Live "Activity" strip (route → agent → tool → QA) | one collapsible line above the composer while working; expandable to the full timeline; **collapsed by default** for simple chats |
| Approval card ("Agent wants to run `bash …`") | inline card with Approve/Deny + risk colour |
| Plan-first preview | inline "here's the plan — Approve to run" |
| 👍/👎 feedback, copy, edit-and-branch | on hover per message |

---

## 4. What to ADD (small, high-value)

Not bloat — these specifically make the decluttered version work better:
1. **A welcoming empty state** — big centred prompt + 3–4 example chips ("Research a topic",
   "Write & run a script", "Make a spreadsheet", "Summarise a file"). Removes the blank-page feel.
2. **A real command palette (⌘/Ctrl-K)** — today ⌘K only makes a new chat. Upgrade it to a
   palette that can: jump to a chat, swap a model, open Settings, run Bench. This is *how* power
   features stay reachable without cluttering the screen.
3. **Toasts** for "budget cap hit", "run stopped", "error — retry?" — instead of stuffing these
   into the message thread.
4. **An end-of-run summary chip** — "Done · tier-2 · 5 steps · $0.0035" under the final answer,
   so cost/▸detail is glanceable.
5. **Right-panel collapsed rail with badges** — thin icons with a dot/count (Files 1 · Tasks ●)
   so you know there's something without it taking space.

## 5. What to REMOVE / demote (off the main screen)
- **All five composer toggles** and the **$/loops boxes** → Run-options popover.
- **Bench** out of the top bar → Settings/▸palette.
- **Export** out of the top bar → chat `···` menu.
- **Memory** and **Models** tabs out of the right panel → Settings.
- **Force QA** as an always-visible toggle (QA auto-runs) → popover only.
- The always-on **"queue as background task"** button → popover/`···`.

Net: the composer goes from **~10 controls to 3** (attach · run-options · send); the right panel
from **6 always-on tabs to 4 contextual sections**; the top bar from **5 items to 3**.

---

## 6. Region-by-region layout (what Stitch should draw)

**Top bar (slim):** left = status pill (`● Backend Live` / `● Working…` pulse / `● Offline`);
right = live **Run cost** + **Settings** gear. Nothing else.

**Left sidebar:** Projects selector · **New chat** · search · chat list (hover: star/rename/delete).

**Center — conversation:**
- *Empty:* centred prompt + example chips + the composer.
- *Active:* message bubbles; a **collapsible Activity strip** just above the composer while working.
- *Composer:* a rounded card with **only** a textarea, an **attach** icon, a **Run-options**
  (sliders) icon, and the **Send** button (→ Stop while running).

**Run-options popover (from the sliders icon):** grouped — *Approval for this run* (segmented
auto/careful/trusted) · *Behavior* (Plan first · Force QA · Parallel · Stream, each with a
one-line tooltip) · *Limits for this run* (Max $ · Max loops, pre-filled) · footer link
"Change defaults in Settings →".

**Right panel — contextual:** collapsed rail by default; **auto-expands** when the first file
is created. Sections (each collapsible, empty ones hidden): **Files** (preview · diff · history ·
copy/download), **Rewind**, **Skills**, **Tasks** (badge when running).

**Settings modal (the one config home):** tabs — **General** (theme, default approval mode) ·
**Limits & cost** (default max $/loops, daily cap, spent today) · **Models** (tier models,
cost-first/fixed strategy, model scout, link to **Model Lab**) · **Memory** (facts: view/add/
forget; rules: approve/reject) · **Security** (access token).

---

## 7. Component states to design (so it's complete)
- Composer: idle · typing · running (Send→Stop) · with attachments.
- Activity strip: hidden (trivial chat) · collapsed one-liner · expanded timeline.
- Run-options popover: default · with a per-run override differing from default (a small "modified" dot).
- Right panel: collapsed rail · expanded with a file open · empty.
- Approval card: safe / risky (colour-coded) with Approve / Deny.
- Toasts: budget cap hit · run stopped · error with Retry.
- Empty state · light + dark · desktop + mobile (side panels become drawers).

## 8. Done-right checklist
- [ ] A first-time user sees only: chat history, a prompt box, Send. No knobs.
- [ ] Every advanced control is reachable in ≤1 click (popover or Settings).
- [ ] No control appears in two places without a clear "default vs this-run" label.
- [ ] The right panel is empty/collapsed until the agent produces something.
- [ ] Sending "hi" returns a clean reply with no visible machinery.

---

## 9. Paste-this-into-Stitch prompt

> Design a calm, decluttered **desktop web UI** (with a mobile layout) for "AGENT // CORE", a
> local AI assistant that chats, writes & runs code, makes documents, and searches the web.
> **Aesthetic:** warm off-white paper background (#FBF7F2), terracotta accent (#C8674F),
> near-black text (#26201C); serif headings (Source Serif), grotesque-sans UI (Geist/Inter),
> JetBrains Mono for code; 16px rounded cards, 1px hairline borders, soft shadows, generous
> whitespace; light + dark mode; Material Symbols (outlined) icons.
>
> **Three columns.** Left = chat history with a Projects selector, a "New chat" button, and
> search. Center = the conversation thread with a single clean composer pinned at the bottom.
> Right = a **contextual panel that is collapsed by default** and only expands when the agent
> produces something (a created file, a plan to approve).
>
> **The composer is minimal:** just a text area, an **attach** icon, a **Run-options** (sliders)
> icon, and a terracotta **Send** button (becomes Stop while running). **No other controls
> inline.** All run tweaks live in the **Run-options popover** that opens from the sliders icon:
> *Approval for this run* (segmented: auto / careful / trusted), *Behavior* (Plan-first, Force QA,
> Parallel, Stream — each a checkbox with a one-line tooltip), and *Limits for this run* (Max $,
> Max loops). A footer link reads "Change defaults in Settings →".
>
> **Top bar is slim:** a connection-status pill on the left; live "Run cost" and a Settings gear
> on the right. Nothing else (no Export, no Bench up here).
>
> **Settings is a modal** with tabs: General (theme, default approval mode), Limits & cost
> (default max $/loops, daily spend cap, spent today), Models (tier models, cost-first vs fixed
> strategy, a "discover models" action, and a link to **Model Lab**), Memory (remembered facts to
> add/forget; proposed rules to approve/reject), and Security (an access token, noted as "only
> needed when hosting off this machine").
>
> **While the agent works,** show a single collapsible "Activity" strip just above the composer
> (e.g. "Planning → Coder writing prime.py → Running…"), expandable to a full step timeline, and
> **collapsed by default** for simple chats. Risky actions appear as an inline **Approval card**
> ("Agent wants to run `bash …` — Approve / Deny") with a risk colour.
>
> **Right panel** is a thin collapsed rail with small badges (Files 1 · Tasks ●) that expands to
> show sections: **Files** (with code preview, diff, version history, copy/download), **Rewind**
> (restore an earlier snapshot), **Skills** (which were used), and **Tasks** (background jobs).
> It auto-expands the first time a file is created.
>
> **Please show these screens:** (1) the empty/welcome state with a centred prompt and 3–4
> example chips; (2) an active conversation with the Activity strip working; (3) the Run-options
> popover open; (4) the Settings modal; (5) the right panel collapsed vs. expanded with a file
> open; (6) the mobile layout where both side panels become drawers; (7) light and dark.

---

### Implementation note (when we build it back into the repo)
This is a **layout + disclosure** change — no backend changes. Every flag already exists in the
Zustand store (`web/src/lib/store.ts`: `mode`, `planFirst`, `review`, `parallel`, `stream`,
`maxUsd`, `maxIter`, `strategy`, `spend`, `theme`, token, plus `files/checkpoints/skills/jobs/
facts/rules`). The work is: move the composer toggles into a popover, move Memory/Models into
`SettingsModal.tsx`, make `RightPanel.tsx` render sections conditionally, and add an empty state
+ command palette. Components touched: `Composer.tsx`, `RightPanel.tsx`, `SettingsModal.tsx`,
`App.tsx`, `Chat.tsx`.
