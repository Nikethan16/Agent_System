---
name: web-frontend
description: Build polished, accessible, single-file web UIs (HTML/CSS/JS) with a distinctive, non-generic visual identity. Use for landing pages, dashboards, components, or any browser UI.
keywords: [html, css, frontend, ui, web, page, landing, dashboard, component, button, form, responsive, javascript, design, aesthetic, theme, layout, typography]
agents: [frontend, coder]
---

# Building a great web frontend

Produce a **single self-contained `index.html`** (inline `<style>` and `<script>`) unless a framework is explicitly requested. It must run by just opening the file.

## Design first — a two-pass method (do this BEFORE coding)

Most AI-built UIs look the same because the model skips design and reaches for defaults. Don't. Spend 30 seconds on an explicit **design plan**, critique it for genericness, then build.

**Pass 1 — write a tiny plan** (in your head or a comment):
- **Palette**: 4–6 named colors. Choose *considered* neutrals — a grey nudged slightly toward the accent hue reads as chosen; a pure mid-grey reads as unconsidered. One accent, used sparingly.
- **Typography as identity**: pick a display face + a body face with a real contrast between them, and a type scale you stay on. Type carries the personality — it is not a neutral delivery vehicle. (CDN webfonts are often blocked; prefer a strong system stack, e.g. `ui-serif`/Georgia for display + `system-ui` for body + `ui-monospace` for data, over a webfont URL that may silently fall back.)
- **Layout concept**: one sentence. What is the organizing idea?
- **Signature element**: the one memorable thing (a distinctive header, a data viz, a motion moment).

**Pass 2 — critique the plan for genericness, then fix it.** Avoid the tells of AI-generated design:
- warm cream (`#F4F1EA`) + serif display + terracotta accent; near-black + a lone acid-green/vermilion pop; broadsheet hairline rules; a purple→blue gradient hero on white; Inter/Space Grotesk as the "safe" face; emoji as section markers; everything centered; `rounded-lg` on everything; an accent bar on rounded cards.
- If any part of your plan is a default you'd produce for *any* page, change it. **Follow the user's stated direction exactly when they give one — their words always win.**

## Quality checklist (do all of these)
- **Layout**: a sensible max-width container, generous whitespace, clear visual hierarchy; let flex/grid + `gap` do the spacing, not stray margins.
- **Responsive**: works on mobile — flexbox/grid, relative units, `<meta viewport>`; wide content (tables/code) scrolls in its own `overflow-x:auto` box so the body never scrolls sideways.
- **Typography**: comfortable line-height (~1.5); running text near 65 chars wide; `text-wrap: balance` on headings; a touch of letter-spacing on uppercase labels; `tabular-nums` where digits align.
- **Color**: a small cohesive palette; concentrate boldness in ONE place and keep everything around it quiet; contrast at WCAG AA.
- **Both themes**: if you offer light/dark, define the palette as CSS custom properties and give the second theme the same care — don't naively invert; keep contrast legible on both grounds.
- **Motion with purpose**: a considered load or hover moment beats scattered effects; excessive animation itself signals AI-generation. Respect `prefers-reduced-motion`.
- **Structure encodes meaning**: numbered markers, eyebrows, dividers only when they carry real information (an actual sequence), not as decoration.
- **Accessibility**: semantic tags (`<header>`, `<main>`, `<button>`), `alt` on images, visible focus states, labels on inputs.
- **Copy is design material**: realistic, concise, active-voice copy — never lorem-ipsum. A control says exactly what it does.
- **Interactivity**: vanilla JS, no external CDNs unless asked; keep it small and commented (explain WHY).

## Process
1. Sketch the design plan (palette / type / layout / signature element); critique it for genericness and revise.
2. Write `index.html` to the workspace, following the revised plan exactly.
3. Sanity-check the markup is well-formed; if a build/test command or `check_page` exists, run it and fix what it flags.
4. Tell the user it's ready and previewable.
