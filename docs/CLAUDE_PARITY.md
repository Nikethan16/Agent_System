# Claude-Parity Roadmap

Goal: make AGENT//CORE feel as close to the **Claude app** as possible. This tracks
the signature Claude features, what we've matched, and what's next (in priority order).

Sources: [Claude features 2026](https://suprmind.ai/hub/claude/features/) ·
[Artifacts help](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them) ·
[Artifacts guide](https://albato.com/blog/publications/how-to-use-claude-artifacts-guide).

Legend: ✅ done · 🟡 partial · ⬜ todo.

## Where we already match Claude
| Claude feature | Us |
|---|---|
| Clean chat, streaming, markdown | ✅ |
| **Syntax-highlighted code + copy button** | ✅ (Batch 1) |
| **Copy response / regenerate** | ✅ (Batch 1) |
| **Artifacts side panel** (code/HTML/md, live preview) | ✅ |
| **Artifact copy / download / expand-to-canvas** | ✅ (Batch 1) |
| Diff view of changes | ✅ (we have it; Claude doesn't expose this) |
| Chat history + rename + search + delete | ✅ |
| Suggested prompts (empty state) | ✅ (Batch 1) |
| Permission/approval controls | ✅ (richer than Claude — security gate) |
| MCP connectors | ✅ |
| Persistent memory across chats | 🟡 (lexical; Claude is richer) |
| Model selector | ✅ (cost-first auto-select — beyond Claude) |
| Multi-agent specialists | ✅ (beyond Claude.ai) |

## Batch 1 — chat polish + artifact canvas ✅ DONE
Syntax highlighting + copy on code blocks · message copy + regenerate · empty-state
suggestion chips · artifact copy/download/**expand-to-canvas modal** · sidebar chat search.

## Batch 2 — attachments + message editing ✅ DONE
- ✅ **File attachments** — attach button → `POST /…/upload`; PDF/text content injected as context.
- ✅ **Edit a previous message → branch** — edit a user turn; truncates from there + re-runs.
- ✅ **"Try fixing" on errors** — error steps in the activity timeline get a one-click fix.

## Batch 3 — Projects + richer artifacts ✅ (mostly)
- ✅ **Projects** — `Project` table; sidebar project selector; shared **instructions + knowledge
  files** injected into every chat in the project (`projects.context` in `chat.py`).
- ✅ **Mermaid + SVG live rendering** in chat code blocks and the artifact canvas.
- 🟡 **Artifact version history** — covered today by per-turn **checkpoints** (workspace rewind);
  per-file version timeline is a future nicety.
- ⬜ **Publish/share link** (local export beyond download) and **React live-run** artifacts —
  deferred (React sandboxed bundling is heavy; low value locally).

## Batch 4 — polish & platform ✅ (essentials)
- ✅ **Settings modal** (theme, default approval mode, default caps, strategy readout).
- ✅ **Keyboard shortcut** ⌘/Ctrl+K = new chat.
- ✅ **Star/favorite chats** (starred sort to top).
- ✅ **Thumbs up/down** feedback (logged to traces).
- 🟡 **Richer persistent memory + memory UI** — lexical/embedding memory works; a management UI is future.
- ⬜ **Full mobile-responsive** layout (collapsible panels on small screens) — deferred (big CSS pass).
- ⬜ **⌘K command palette** (beyond new-chat), chat folders.

## What's genuinely left (small)
1. Full mobile responsiveness.
2. Per-file artifact version timeline + publish-link.
3. React live-run artifacts (heavy; optional).
4. A memory-management UI + ⌘K command palette.

Everything else from the Claude-parity plan is implemented.
