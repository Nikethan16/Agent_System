import { useState } from "react";
import { useStore } from "../lib/store";
import ProjectModal from "./ProjectModal";

export default function Sidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void } = {}) {
  const { sessions, currentId, newSession, selectSession, deleteSession, renameSession, resolved, strategy,
          projects, activeProject, setActiveProject, createProject, toggleStar, theme, toggleTheme } = useStore();
  const [projModal, setProjModal] = useState(false);
  const dark = theme === "dark";
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const commit = (id: string) => { if (draft.trim()) renameSession(id, draft.trim()); setEditing(null); };
  const shown = query.trim()
    ? sessions.filter((s) => (s.title || "").toLowerCase().includes(query.toLowerCase()))
    : sessions;

  return (
    <aside className={`fixed left-0 top-0 h-screen w-sidebar-width flex flex-col border-r border-light-border dark:border-dark-border bg-surface dark:bg-dark-surface py-5 z-40 transition-transform duration-200 md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
      <div className="px-5 mb-6 flex items-center gap-3">
        <div className="w-8 h-8 bg-accent-terracotta rounded-lg flex items-center justify-center text-white font-bold">A</div>
        <div>
          <h1 className="font-display text-[16px] font-bold tracking-tight leading-none">AGENT <span className="text-accent-terracotta">//</span> CORE</h1>
          <p className="text-[10px] uppercase tracking-[0.18em] text-light-muted mt-1">Local Intelligence</p>
        </div>
      </div>

      <div className="px-3 mb-3">
        <div className="flex items-center gap-1.5">
          <select value={activeProject}
            onChange={(e) => { if (e.target.value === "__new__") { const n = prompt("Project name"); if (n) createProject(n); } else setActiveProject(e.target.value); }}
            className="flex-1 text-xs bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1.5 outline-none">
            <option value="">All chats</option>
            {projects.map((p) => <option key={p.id} value={p.id}>📁 {p.name}</option>)}
            <option value="__new__">＋ New project…</option>
          </select>
          {activeProject && (
            <button onClick={() => setProjModal(true)} title="Project settings (instructions + knowledge)"
              className="p-1.5 rounded-lg text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container dark:hover:bg-dark-surface">
              <span className="material-symbols-outlined text-[18px]">tune</span>
            </button>
          )}
        </div>
      </div>

      <div className="px-3 mb-4">
        <button onClick={() => { newSession(); onClose?.(); }}
          className="w-full flex items-center justify-center gap-2 py-2.5 bg-surface-container-high dark:bg-dark-bg hover:bg-surface-container-highest text-on-surface dark:text-dark-text font-medium rounded-lg transition active:scale-95">
          <span className="material-symbols-outlined text-[20px]">add_circle</span> New chat
        </button>
      </div>
      {projModal && activeProject && <ProjectModal pid={activeProject} onClose={() => setProjModal(false)} />}

      <div className="px-3 mb-2">
        <div className="flex items-center gap-2 px-2.5 py-1.5 bg-surface-container-low dark:bg-dark-bg rounded-lg border border-light-border dark:border-dark-border">
          <span className="material-symbols-outlined text-light-muted text-[16px]">search</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search chats"
            className="bg-transparent outline-none text-xs w-full placeholder-light-muted" />
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto scrollbar px-2 space-y-0.5">
        {shown.map((s) => (
          <div key={s.id} role="button" tabIndex={0} aria-label={`Open chat ${s.title || "Untitled"}`}
            onClick={() => { selectSession(s.id); onClose?.(); }}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectSession(s.id); onClose?.(); } }}
            className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm transition ${s.id === currentId ? "bg-surface-container dark:bg-dark-bg font-medium" : "text-on-surface-variant dark:text-light-muted hover:bg-surface-container-low dark:hover:bg-dark-bg/50"}`}>
            <span className="material-symbols-outlined text-[18px] text-light-muted">{s.id === currentId ? "chat_bubble" : "history"}</span>
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

      <div className="px-3 pt-3 mt-auto border-t border-light-border dark:border-dark-border">
        <div className="flex items-center gap-2 px-3 py-2.5 bg-surface-container-low dark:bg-dark-bg rounded-xl border border-light-border/60 dark:border-dark-border">
          <span className="material-symbols-outlined text-accent-terracotta">smart_toy</span>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-bold truncate">{strategy === "cheapest" ? (resolved.tier2 || "auto") : "fixed tiers"}</p>
            <p className="text-[10px] text-light-muted uppercase tracking-tight">{strategy === "cheapest" ? "cost-first" : "per-tier"}</p>
          </div>
          <button onClick={toggleTheme} className="p-1.5 rounded-lg text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container dark:hover:bg-dark-surface transition">
            <span className="material-symbols-outlined text-[18px]">{dark ? "light_mode" : "dark_mode"}</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
