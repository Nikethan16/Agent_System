---
name: web-frontend
description: Build polished, accessible, single-file web UIs (HTML/CSS/JS). Use for landing pages, dashboards, components, or any browser UI.
keywords: [html, css, frontend, ui, web, page, landing, dashboard, component, button, form, responsive, javascript]
agents: [frontend, coder]
---

# Building a great web frontend

Produce a **single self-contained `index.html`** (inline `<style>` and `<script>`) unless a framework is explicitly requested. It must run by just opening the file.

## Quality checklist (do all of these)
- **Layout**: a sensible max-width container, generous whitespace, clear visual hierarchy.
- **Responsive**: works on mobile — use flexbox/grid, relative units, and a `<meta viewport>`.
- **Typography**: one clean system/web font stack; comfortable line-height (~1.5); readable sizes.
- **Color**: a small, cohesive palette (1 accent + neutrals). Sufficient contrast (WCAG AA).
- **Polish**: rounded corners, subtle shadows/borders, smooth `transition` on hover/focus states.
- **Accessibility**: semantic tags (`<header>`, `<main>`, `<button>`), `alt` on images, focus styles, labels on inputs.
- **Interactivity**: vanilla JS, no external CDNs unless asked; keep it small and commented.
- **No lorem-ipsum dumps**: write realistic, concise copy.

## Process
1. Write `index.html` to the workspace.
2. Sanity-check the markup is well-formed; if a build/test command exists, run it.
3. Tell the user it's ready and previewable.
