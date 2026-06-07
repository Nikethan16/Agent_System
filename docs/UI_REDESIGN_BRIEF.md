# AGENT // CORE — UI Redesign Brief (for Google Stitch / v0 / Figma-AI)

A ready-to-use design prompt + rationale to clean up the AGENT//CORE web UI. The
**visual language stays** (warm-paper + terracotta, fonts below). What changes is the
**information architecture**: stop showing every control at once; reveal each feature
only when it's relevant (progressive disclosure).

---

## 0. Paste-this-into-Stitch prompt (the short version)

> Design a desktop web UI for "AGENT // CORE", a local multi-agent assistant (like a
> chat app that can also run code and use tools). Aesthetic: warm off-white paper
> background (#FBF7F2), terracotta accent (#C8674F), near-black text; headings in a
> serif (Source Serif), body in a clean grotesque sans (Geist/Inter), code in JetBrains
> Mono; generous whitespace, soft rounded cards (16px), subtle borders, no heavy
> shadows. Light + dark mode.
>
> Three-column layout: (1) left sidebar = chat history + "New chat"; (2) center =
> conversation thread with a single clean message composer at the bottom; (3) right =
> a contextual panel that is *collapsed by default* and only expands when there's
> something to show (files the agent created, a plan to approve, etc.).
>
> **The composer must be minimal by default**: just a text box, an attach button, and a
> send button. All advanced run-controls (approval mode, plan-first, QA, parallel,
> streaming, per-run budget, loop cap) live behind a single small "Run options" control
> (a gear/sliders icon that opens a popover) — NOT shown inline. The top bar shows only:
> connection status, run cost, and a settings gear. Settings (a modal) holds defaults:
> theme, default approval mode, default budget + loop cap, daily spend cap, model
> strategy, access token. Don't duplicate any control in two places.
>
> Show me: the default empty state, an active conversation with the agent working
> (a compact live "activity" strip, collapsible), the Run-options popover, the Settings
> modal, and the right panel in both its collapsed and expanded (showing a created file)
> states. Desktop first; include a mobile layout where the side panels become drawers.

Everything below is the detail Stitch (or a designer) needs to get it right.

---

## 1. Product context (what the app is)
A single-user, local "agent" app. The user types a task; the system classifies its
difficulty, then either one specialist agent handles it or a lead agent plans it and
delegates steps to worker agents. It can read/write files, run code, search the web,
remember facts across chats, and asks for human approval on risky actions. Output often
includes **artifacts** (files: code, markdown, docs) the user opens in a side panel.

**Primary job-to-be-done:** "Give the agent a task in one box and watch it work; only
deal with settings/controls when I actually need them."

## 2. The problem with the current UI
- The **composer is overloaded**: approval mode (auto/careful/trusted), Plan-First, Force
  QA, Parallel, Stream toggles, a `$` budget box and a `loops` box are ALL inline, every
  time, even for a one-word "hi".
- These **duplicate Settings**, which already has approval mode, max cost, max loops,
  spend, and access token. Two homes for the same control = confusion.
- The **right panel always shows 6 tabs** (Files, Rewind, Memory, Skills, Tasks, Models)
  even when most are empty and irrelevant to the moment.
- The **top bar** mixes a power feature (Bench / Model Lab) with everyday actions.
- Net effect: a new user can't tell what matters. Everything competes for attention.

## 3. Design principles
1. **Progressive disclosure.** Show the 20% used 80% of the time; tuck the rest one click
   away. Default = minimal.
2. **One home per control.** A setting lives in exactly one place (its default in
   Settings; an optional per-run override in the Run-options popover — clearly labelled
   "for this run only").
3. **Context-driven panels.** The right panel and the activity feed appear when there's
   content; otherwise they stay out of the way.
4. **Calm visual hierarchy.** Primary action (send) is the only filled/terracotta button
   on the screen at rest.
5. **Keep the brand.** Same palette, fonts, rounded cards, light/dark — only the layout
   and disclosure change.

## 4. Information architecture — where each thing lives

| Control / feature | Today | Proposed home | Visible when |
|---|---|---|---|
| Text input, attach, send | Composer | **Composer** (only these) | always |
| Approval mode (auto/careful/trusted) | Composer + Settings | **Settings** (default) + Run-options popover (per-run) | popover on demand |
| Plan-first, Force QA, Parallel, Stream | Composer | **Run-options popover** | popover on demand |
| Max $ per run, Max loops | Composer + Settings | **Settings** (default) + Run-options (per-run override) | popover on demand |
| Run cost (live) | Top bar | **Top bar** (keep) | always |
| Daily spend cap / spent today | Settings | **Settings** | settings |
| Theme, access token, model strategy | Settings | **Settings** | settings |
| Export chat | Top bar | **Chat overflow menu (···)** | menu |
| Bench / Model Lab | Top bar | **Settings → "Advanced / Model Lab"** or a command palette | advanced |
| Files (artifacts) | Right tab | **Right panel — primary**, auto-opens when a file is created | when artifacts exist |
| Rewind (checkpoints) | Right tab | Right panel section (collapsible) | when checkpoints exist |
| Memory | Right tab | **Settings → Memory** OR right-panel secondary tab | on demand |
| Skills | Right tab | Right-panel secondary tab (read-mostly) | on demand |
| Tasks (background jobs) | Right tab | Right-panel section, badge when jobs run | when jobs exist |
| Models | Right tab | **Settings → Models** (it's configuration, not per-chat) | settings |

Guiding idea: **per-chat content** (files, plan-to-approve, running jobs) → right panel;
**configuration** (models, memory rules, strategy, token) → Settings; **per-run tweaks**
→ the Run-options popover.

## 5. Region-by-region spec

### Top bar (slim)
Left: a status pill — `● Backend Live` / `● Working…` (terracotta pulse) / `● Offline`.
Right: live **Run cost** ($0.0000), then a **Settings gear**. That's it. Move Export into
a per-chat `···` overflow; move Bench into Settings → Advanced.

### Left sidebar (unchanged in spirit)
"New chat" button, search, chat list with rename/star/delete on hover. Good as is.

### Center — conversation
- **Empty state:** big centered prompt + 3–4 example suggestion chips ("Summarize a file",
  "Write & run a script", "Research a topic"). One clean composer below.
- **Active:** message bubbles. While the agent works, a **single collapsible "Activity"
  strip** appears just above the composer (e.g. "Planning → Coder writing add.py →
  Running…"), expandable to the full step timeline. Collapsed by default for simple chats.
- **Composer (the key change):** a rounded card with only: textarea, an **attach** icon,
  a **Run-options** icon (sliders), and the **send** button. A small "queue as background
  task" action can live in the `···`/long-press, not as a always-on button.

### Run-options popover (opens from the sliders icon on the composer)
A small panel, grouped:
- **Approval for this run:** auto / careful / trusted (segmented).
- **Behavior:** Plan first ▢ · Force QA ▢ · Run subtasks in parallel ▢ · Stream tokens ▢
  (each with a one-line helper tooltip).
- **Limits for this run:** Max $ [   ] · Max loops [   ] (pre-filled from Settings
  defaults; editing affects this run only).
- Footer link: "Change defaults in Settings →".

### Right panel — contextual
- **Collapsed by default.** A thin rail with icons + a dot/badge when a section has
  content (e.g. Files: 1, Jobs: running).
- **Files** is the primary section and **auto-expands the panel** the first time the agent
  creates an artifact. Sections: Files, Rewind, Skills, Tasks. (Memory + Models move to
  Settings.) Each section is collapsible; empty ones are hidden or greyed.

### Settings modal (the single config home)
Tabs or grouped sections:
- **General:** theme, default approval mode.
- **Limits & cost:** default max $/run, default max loops, **daily spend cap**, spent
  today.
- **Models:** tier models / strategy (cost-first vs fixed), link to Model Lab (Bench).
- **Memory:** view/add/forget facts, approve/reject rules.
- **Security/Deploy:** access token (note "only needed when hosting off this machine").

## 6. Component states to design
- Composer: idle / typing / running (send→stop) / with attachments.
- Activity strip: hidden (simple chat) / collapsed one-liner / expanded timeline.
- Approval card (inline in thread): "Agent wants to run `bash …` — Approve / Deny", with
  risk colour.
- Right panel: collapsed rail / expanded with a file open (code preview, copy/download) /
  empty.
- Run-options popover: open, with a per-run override differing from default (show a tiny
  "modified" dot).
- Toasts: budget cap hit, run stopped, error with a "retry" affordance.

## 7. Visual system (keep)
- **Bg paper** `#FBF7F2`; surface white; **accent terracotta** `#C8674F`; text near-black
  `#26201C`; muted `#8A817A`. Dark mode: near-black bg, warm off-white text, same accent.
- **Fonts:** display/serif = Source Serif; UI sans = Geist (or Inter); mono = JetBrains
  Mono. Material Symbols (outlined) for icons.
- **Shape/space:** 16px card radius, 1px hairline borders, soft/low shadows, roomy padding,
  small uppercase tracked labels for section headers.

## 8. Acceptance criteria (how we'll know it's better)
- A first-time user sees only: history, a prompt box, send. No knobs.
- Every advanced control is reachable in ≤1 click (Run-options popover or Settings).
- No control appears in two places without a clear "default vs this-run" distinction.
- Right panel is empty/collapsed until the agent produces something.
- Sending a trivial "hi" shows a clean reply with no visible machinery.

---

### Implementation note (for whoever builds it back into this repo)
This is a layout/disclosure change only — the existing components already exist:
`Composer.tsx`, `SettingsModal.tsx`, `RightPanel.tsx` (+ Files/Checkpoints/Memory/Skills/
Jobs/ModelRail), and the Zustand store in `lib/store.ts` already holds every flag
(`mode`, `planFirst`, `review`, `parallel`, `stream`, `maxUsd`, `maxIter`, `strategy`,
`spend`, `theme`, token). The redesign mostly **moves** these into a popover + Settings
tabs and **conditionally renders** the right panel — no backend changes required.
