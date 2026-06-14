import { useState } from "react";
import { useStore } from "../lib/store";
import ProjectModal from "./ProjectModal";
import Sunburst from "./Sunburst";

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

  return (
    <aside className={`fixed left-0 top-0 h-screen w-sidebar-width flex flex-col bg-claude-sidebar dark:bg-claude-sidebar-dark py-4 z-40 transition-transform duration-200 md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
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

      <p className="px-5 text-[11px] uppercase tracking-widest text-light-muted mb-1.5">Recents</p>
      <nav className="flex-1 overflow-y-auto scrollbar px-2 space-y-0.5">
        {shown.map((s) => (
          <div key={s.id} role="button" tabIndex={0} aria-label={`Open chat ${s.title || "Untitled"}`}
            onClick={() => { selectSession(s.id); onClose?.(); }}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectSession(s.id); onClose?.(); } }}
            className={`group flex items-center gap-2 px-3 py-2 rounded-xl cursor-pointer text-[13px] transition ${s.id === currentId ? "bg-white dark:bg-dark-surface font-medium shadow-sm" : "text-on-surface-variant dark:text-light-muted hover:bg-white/60 dark:hover:bg-dark-surface/60"}`}>
            {editing === s.id ? (
              <input autoFocus value={draft}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={() => commit(s.id)}
                onKeyDown={(e) => { if (e.key === "Enter") commit(s.id); if (e.key === "Escape") setEditing(null); }}
                className="flex-1 bg-white dark:bg-dark-bg border border-light-border dark:border-dark-border rounded px-1.5 py-0.5 text-sm outline-none" />
            ) : (
              <span className="truncate flex-1" title="Double-click to rename"
                onDoubleClick={(e) => { e.stopPropagation(); setEditing(s.id); setDraft(s.title || ""); }}>
                {s.title || "Untitled"}
              </span>
            )}
            <span role="button" tabIndex={0} aria-label={s.starred ? "Unstar chat" : "Star chat"}
              onClick={(e) => { e.stopPropagation(); toggleStar(s.id); }}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); e.preventDefault(); toggleStar(s.id); } }}
              title="Star"
              className={`material-symbols-outlined text-[15px] ${s.starred ? "text-accent-terracotta opacity-100" : "text-light-muted opacity-0 group-hover:opacity-100 hover:text-accent-terracotta"}`}
              style={s.starred ? { fontVariationSettings: "'FILL' 1" } : undefined}>star</span>
            <span role="button" tabIndex={0} aria-label="Delete chat"
              onClick={(e) => { e.stopPropagation(); if (confirm("Delete this chat and its files?")) deleteSession(s.id); }}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); e.preventDefault(); if (confirm("Delete this chat and its files?")) deleteSession(s.id); } }}
              title="Delete"
              className="material-symbols-outlined text-[16px] opacity-0 group-hover:opacity-100 text-light-muted hover:text-red-500">close</span>
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
