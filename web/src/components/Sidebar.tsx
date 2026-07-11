import { useState } from "react";
import { useStore } from "../lib/store";
import ProjectModal from "./ProjectModal";
import Sunburst from "./Sunburst";

// Short "3h ago" / "yesterday" / "Jul 4" label from an ISO timestamp.
function relTime(iso?: string): string {
  const t = iso ? Date.parse(iso) : NaN;
  if (Number.isNaN(t)) return "";
  const s = (Date.now() - t) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  const d = Math.floor(s / 86400);
  if (d === 1) return "yesterday";
  if (d < 7) return `${d}d ago`;
  return new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// Which recency bucket a chat falls in (by last activity). Starred chats are pulled
// into "Pinned" regardless of date.
const BUCKET_ORDER = ["Pinned", "Today", "Yesterday", "Previous 7 days", "Older"];
function bucketOf(iso?: string): string {
  const t = iso ? Date.parse(iso) : NaN;
  if (Number.isNaN(t)) return "Older";
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (t >= startToday) return "Today";
  if (t >= startToday - 86400000) return "Yesterday";
  if (t >= startToday - 7 * 86400000) return "Previous 7 days";
  return "Older";
}

export default function Sidebar({ open = false, onClose, email = "", onOpenSettings, onLogout }:
  { open?: boolean; onClose?: () => void; email?: string; onOpenSettings?: () => void; onLogout?: () => void } = {}) {
  const { sessions, currentId, newSession, selectSession, deleteSession, renameSession,
          projects, activeProject, setActiveProject, createProject, toggleStar, theme, toggleTheme } = useStore();
  const [projModal, setProjModal] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const dark = theme === "dark";
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const commit = (id: string) => { if (draft.trim()) renameSession(id, draft.trim()); setEditing(null); };
  const shown = query.trim()
    ? sessions.filter((s) => (s.title || "").toLowerCase().includes(query.toLowerCase()))
    : sessions;
  const projName = (id: string) => projects.find((p) => p.id === id)?.name || "";

  // Bucket chats by recency (starred → Pinned), newest first within each bucket, so
  // RECENTS reads as a dated list instead of one long undifferentiated stack.
  const groups: Record<string, typeof shown> = {};
  for (const s of shown) {
    const key = s.starred ? "Pinned" : bucketOf(s.updated_at);
    (groups[key] ||= []).push(s);
  }
  for (const k of Object.keys(groups)) {
    groups[k].sort((a, b) => Date.parse(b.updated_at || "") - Date.parse(a.updated_at || ""));
  }
  const orderedGroups = BUCKET_ORDER.filter((k) => groups[k]?.length);

  return (
    <aside className={`fixed left-0 top-0 h-screen w-sidebar-width max-w-[85vw] flex flex-col bg-claude-sidebar dark:bg-claude-sidebar-dark py-4 z-40 transition-transform duration-200 md:translate-x-0 md:max-w-none ${open ? "translate-x-0" : "-translate-x-full"}`}>
      <div className="px-4 mb-5 flex items-center gap-2.5">
        <Sunburst size={26} />
        <h1 className="font-headline text-[15px] font-semibold tracking-tight leading-none">AGENT <span className="text-accent-terracotta">//</span> CORE</h1>
      </div>

      <div className="px-3 mb-1">
        <button onClick={() => { newSession(); onClose?.(); }}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 text-accent-terracotta hover:bg-white/60 dark:hover:bg-dark-surface font-medium rounded-xl transition text-[14px]">
          <span className="material-symbols-outlined text-[20px]">edit_square</span> New chat
        </button>
      </div>

      <div className="px-3 mb-3">
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl text-light-muted">
          <span className="material-symbols-outlined text-[18px]">search</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search chats"
            className="bg-transparent outline-none text-[13px] w-full placeholder-light-muted text-on-surface dark:text-dark-text" />
        </div>
      </div>

      <div className="px-3 mb-2">
        <div className="flex items-center gap-1.5">
          <select value={activeProject}
            onChange={(e) => { if (e.target.value === "__new__") { const n = prompt("Project name"); if (n) createProject(n); } else setActiveProject(e.target.value); }}
            className="flex-1 text-[12px] bg-transparent hover:bg-white/50 dark:hover:bg-dark-surface rounded-lg px-2 py-1.5 outline-none text-on-surface-variant dark:text-light-muted cursor-pointer">
            <option value="">All chats</option>
            {projects.map((p) => <option key={p.id} value={p.id}>📁 {p.name}</option>)}
            <option value="__new__">＋ New project…</option>
          </select>
          {activeProject && (
            <button onClick={() => setProjModal(true)} title="Project settings (instructions + knowledge)"
              className="p-1.5 rounded-lg text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-white/60 dark:hover:bg-dark-surface">
              <span className="material-symbols-outlined text-[18px]">tune</span>
            </button>
          )}
        </div>
      </div>
      {projModal && activeProject && <ProjectModal pid={activeProject} onClose={() => setProjModal(false)} />}

      <nav className="flex-1 overflow-y-auto scrollbar px-2 pb-2">
        {shown.length === 0 && (
          <p className="px-3 py-6 text-center text-[12px] text-light-muted">
            {query.trim() ? "No chats match." : "No chats yet."}
          </p>
        )}
        {orderedGroups.map((g) => (
          <div key={g} className="mb-1">
            <p className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-[0.14em] text-light-muted font-semibold flex items-center gap-1.5">
              {g === "Pinned" && <span className="material-symbols-outlined text-[12px] text-accent-terracotta" style={{ fontVariationSettings: "'FILL' 1" }}>star</span>}
              {g}
            </p>
            {groups[g].map((s) => {
              const proj = !activeProject ? projName(s.project_id) : "";
              const when = relTime(s.updated_at);
              return (
                <div key={s.id} role="button" tabIndex={0} aria-label={`Open chat ${s.title || "Untitled"}`}
                  onClick={() => { selectSession(s.id); onClose?.(); }}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectSession(s.id); onClose?.(); } }}
                  className={`group flex items-start gap-2 px-3 py-2 rounded-xl cursor-pointer transition ${s.id === currentId ? "bg-white dark:bg-dark-surface shadow-sm" : "hover:bg-white/60 dark:hover:bg-dark-surface/60"}`}>
                  <div className="min-w-0 flex-1">
                    {editing === s.id ? (
                      <input autoFocus value={draft}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => setDraft(e.target.value)}
                        onBlur={() => commit(s.id)}
                        onKeyDown={(e) => { if (e.key === "Enter") commit(s.id); if (e.key === "Escape") setEditing(null); }}
                        className="w-full bg-white dark:bg-dark-bg border border-light-border dark:border-dark-border rounded px-1.5 py-0.5 text-[13px] outline-none" />
                    ) : (
                      <>
                        <div className={`truncate text-[13px] leading-tight ${s.id === currentId ? "font-semibold text-on-surface dark:text-dark-text" : "text-on-surface-variant dark:text-light-muted"}`}
                          title="Double-click to rename"
                          onDoubleClick={(e) => { e.stopPropagation(); setEditing(s.id); setDraft(s.title || ""); }}>
                          {s.title || "Untitled"}
                        </div>
                        {(when || proj) && (
                          <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-light-muted truncate">
                            {proj && <span className="text-accent-deep dark:text-accent-terracotta truncate">{proj}</span>}
                            {proj && when && <span aria-hidden>·</span>}
                            {when && <span className="tabular-nums">{when}</span>}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  <span role="button" tabIndex={0} aria-label={s.starred ? "Unstar chat" : "Star chat"}
                    onClick={(e) => { e.stopPropagation(); toggleStar(s.id); }}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); e.preventDefault(); toggleStar(s.id); } }}
                    title="Star"
                    className={`material-symbols-outlined text-[15px] mt-0.5 shrink-0 ${s.starred ? "text-accent-terracotta opacity-100" : "text-light-muted opacity-0 group-hover:opacity-100 hover:text-accent-terracotta"}`}
                    style={s.starred ? { fontVariationSettings: "'FILL' 1" } : undefined}>star</span>
                  <span role="button" tabIndex={0} aria-label="Delete chat"
                    onClick={(e) => { e.stopPropagation(); if (confirm("Delete this chat and its files?")) deleteSession(s.id); }}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); e.preventDefault(); if (confirm("Delete this chat and its files?")) deleteSession(s.id); } }}
                    title="Delete"
                    className="material-symbols-outlined text-[16px] mt-0.5 shrink-0 opacity-0 group-hover:opacity-100 text-light-muted hover:text-red-500">close</span>
                </div>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="px-3 pt-2 mt-auto relative">
        <button onClick={() => setAccountOpen((o) => !o)} aria-label="Account menu"
          className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl hover:bg-white/60 dark:hover:bg-dark-surface transition">
          <span className="w-7 h-7 rounded-full bg-accent-terracotta text-white flex items-center justify-center text-[12px] font-semibold uppercase shrink-0">{(email || "A").charAt(0)}</span>
          <span className="flex-1 min-w-0 text-left text-[13px] truncate">{email || "Account"}</span>
          <span className="material-symbols-outlined text-[18px] text-light-muted">more_horiz</span>
        </button>
        {accountOpen && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setAccountOpen(false)} />
            <div className="absolute bottom-[52px] left-3 right-3 bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-xl shadow-xl p-1 z-50 fadeup">
              <button onClick={() => { onOpenSettings?.(); setAccountOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm hover:bg-surface-container-low dark:hover:bg-dark-bg text-left">
                <span className="material-symbols-outlined text-[18px] text-light-muted">settings</span>Settings
              </button>
              <button onClick={() => toggleTheme()}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm hover:bg-surface-container-low dark:hover:bg-dark-bg text-left">
                <span className="material-symbols-outlined text-[18px] text-light-muted">{dark ? "light_mode" : "dark_mode"}</span>{dark ? "Light mode" : "Dark mode"}
              </button>
              {onLogout && (
                <button onClick={() => { onLogout(); setAccountOpen(false); }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm hover:bg-surface-container-low dark:hover:bg-dark-bg text-left text-red-500">
                  <span className="material-symbols-outlined text-[18px]">logout</span>Log out
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
