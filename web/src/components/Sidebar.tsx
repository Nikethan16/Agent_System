import { useState } from "react";
import { useStore } from "../lib/store";
import ProjectModal from "./ProjectModal";
import NewProjectModal from "./NewProjectModal";
import Sunburst from "./Sunburst";

export default function Sidebar({ open = false, onClose, email = "", onOpenSettings, onLogout, onOpenArtifacts }:
  { open?: boolean; onClose?: () => void; email?: string; onOpenSettings?: () => void;
    onLogout?: () => void; onOpenArtifacts?: () => void } = {}) {
  const { sessions, currentId, newSession, selectSession, deleteSession, renameSession,
          projects, activeProject, setActiveProject, toggleStar, theme, toggleTheme,
          connected, spend } = useStore();
  const [projModal, setProjModal] = useState(false);
  const [newProj, setNewProj] = useState(false);
  const [projMenu, setProjMenu] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [nav, setNav] = useState<"home" | "projects" | "artifacts" | "scheduled">("home");
  const dark = theme === "dark";
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const commit = (id: string) => { if (draft.trim()) renameSession(id, draft.trim()); setEditing(null); };

  // Two buckets only, matching the design: Pinned (starred) and Recents (everything else),
  // newest-first.
  const pinned = sessions.filter((s) => s.starred)
    .sort((a, b) => Date.parse(b.updated_at || "") - Date.parse(a.updated_at || ""));
  const recents = sessions.filter((s) => !s.starred)
    .sort((a, b) => Date.parse(b.updated_at || "") - Date.parse(a.updated_at || ""));

  const name = ((email.split("@")[0] || "").replace(/[0-9._-]+$/, "") || "Account");
  const display = name.charAt(0).toUpperCase() + name.slice(1);
  const today = spend?.spent_today || 0;

  const NavItem = ({ id, icon, label, onClick }: { id: typeof nav; icon: string; label: string; onClick: () => void }) => (
    <button onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] transition ${nav === id
        ? "bg-accent-terracotta/12 text-accent-deep dark:text-accent-terracotta font-semibold"
        : "text-on-surface-variant dark:text-light-muted hover:bg-white/60 dark:hover:bg-dark-surface hover:text-on-surface dark:hover:text-dark-text"}`}>
      <span className="material-symbols-outlined text-[19px]">{icon}</span>{label}
    </button>
  );

  const ChatRow = ({ s }: { s: any }) => (
    <div role="button" tabIndex={0} aria-label={`Open chat ${s.title || "Untitled"}`}
      onClick={() => { selectSession(s.id); setNav("home"); onClose?.(); }}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectSession(s.id); onClose?.(); } }}
      className={`group flex items-center gap-2.5 pl-3 pr-2 py-1.5 rounded-lg cursor-pointer transition ${s.id === currentId ? "bg-white dark:bg-dark-surface shadow-sm" : "hover:bg-white/60 dark:hover:bg-dark-surface/60"}`}>
      <span className="material-symbols-outlined text-[16px] text-light-muted shrink-0">chat_bubble</span>
      {editing === s.id ? (
        <input autoFocus value={draft} onClick={(e) => e.stopPropagation()}
          onChange={(e) => setDraft(e.target.value)} onBlur={() => commit(s.id)}
          onKeyDown={(e) => { if (e.key === "Enter") commit(s.id); if (e.key === "Escape") setEditing(null); }}
          className="flex-1 min-w-0 bg-white dark:bg-dark-bg border border-light-border dark:border-dark-border rounded px-1.5 py-0.5 text-[13px] outline-none" />
      ) : (
        <span className={`flex-1 min-w-0 truncate text-[13px] ${s.id === currentId ? "font-semibold text-on-surface dark:text-dark-text" : "text-on-surface-variant dark:text-light-muted"}`}
          onDoubleClick={(e) => { e.stopPropagation(); setEditing(s.id); setDraft(s.title || ""); }}>
          {s.title || "Untitled"}
        </span>
      )}
      <span role="button" tabIndex={0} aria-label={s.starred ? "Unstar" : "Star"} title="Star"
        onClick={(e) => { e.stopPropagation(); toggleStar(s.id); }}
        className={`material-symbols-outlined text-[15px] shrink-0 ${s.starred ? "text-accent-terracotta opacity-100" : "text-light-muted opacity-0 group-hover:opacity-100 hover:text-accent-terracotta"}`}
        style={s.starred ? { fontVariationSettings: "'FILL' 1" } : undefined}>star</span>
      <span role="button" tabIndex={0} aria-label="Delete" title="Delete"
        onClick={(e) => { e.stopPropagation(); if (confirm("Delete this chat and its files?")) deleteSession(s.id); }}
        className="material-symbols-outlined text-[16px] shrink-0 opacity-0 group-hover:opacity-100 text-light-muted hover:text-red-500">close</span>
    </div>
  );

  return (
    <aside className={`fixed left-0 top-0 h-screen w-sidebar-width max-w-[85vw] flex flex-col bg-claude-sidebar dark:bg-claude-sidebar-dark py-4 z-40 transition-transform duration-200 md:translate-x-0 md:max-w-none ${open ? "translate-x-0" : "-translate-x-full"}`}>
      <div className="px-4 mb-3 flex items-center gap-2.5">
        <Sunburst size={26} />
        <h1 className="font-headline text-[15px] font-semibold tracking-tight leading-none">AGENT <span className="text-accent-terracotta">//</span> CORE</h1>
      </div>

      {/* New chat */}
      <div className="px-3 mb-1.5">
        <button onClick={() => { newSession(); setNav("home"); onClose?.(); }}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl border border-light-border dark:border-dark-border bg-white/70 dark:bg-dark-surface hover:border-accent-terracotta text-accent-deep dark:text-accent-terracotta font-medium transition text-[13.5px]">
          <span className="material-symbols-outlined text-[19px]">edit_square</span> New chat
          <span className="ml-auto text-[10.5px] font-code text-light-muted border border-light-border dark:border-dark-border rounded px-1.5 py-px">⌘K</span>
        </button>
      </div>

      {/* Primary nav */}
      <nav className="px-3 flex flex-col gap-0.5">
        <NavItem id="home" icon="home" label="Home" onClick={() => { newSession(); setNav("home"); onClose?.(); }} />
        <div className="relative">
          <NavItem id="projects" icon="work" label="Projects" onClick={() => { setNav("projects"); setProjMenu((o) => !o); }} />
          {projMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setProjMenu(false)} />
              <div className="absolute left-2 right-0 top-full mt-1 bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-xl shadow-xl p-1 z-50 fadeup">
                <button onClick={() => { setActiveProject(""); setProjMenu(false); }}
                  className={`w-full text-left px-3 py-1.5 rounded-lg text-[13px] hover:bg-surface-container-low dark:hover:bg-dark-bg ${!activeProject ? "font-semibold" : ""}`}>All chats</button>
                {projects.map((p) => (
                  <button key={p.id} onClick={() => { setActiveProject(p.id); setProjMenu(false); }}
                    className={`w-full text-left px-3 py-1.5 rounded-lg text-[13px] truncate hover:bg-surface-container-low dark:hover:bg-dark-bg ${activeProject === p.id ? "font-semibold" : ""}`}>{p.name}</button>
                ))}
                <div className="h-px bg-light-border/60 dark:bg-dark-border my-1" />
                <button onClick={() => { setNewProj(true); setProjMenu(false); }}
                  className="w-full text-left px-3 py-1.5 rounded-lg text-[13px] text-accent-deep dark:text-accent-terracotta hover:bg-surface-container-low dark:hover:bg-dark-bg flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px]">add</span>New project…</button>
                {activeProject && (
                  <button onClick={() => { setProjModal(true); setProjMenu(false); }}
                    className="w-full text-left px-3 py-1.5 rounded-lg text-[13px] hover:bg-surface-container-low dark:hover:bg-dark-bg flex items-center gap-2">
                    <span className="material-symbols-outlined text-[16px]">tune</span>Project settings</button>
                )}
              </div>
            </>
          )}
        </div>
        <NavItem id="artifacts" icon="deployed_code" label="Artifacts" onClick={() => { setNav("artifacts"); onOpenArtifacts?.(); }} />
        <NavItem id="scheduled" icon="schedule" label="Scheduled" onClick={() => { setNav("scheduled"); onOpenSettings?.(); }} />
      </nav>

      {projModal && activeProject && <ProjectModal pid={activeProject} onClose={() => setProjModal(false)} />}
      {newProj && <NewProjectModal onClose={() => setNewProj(false)} />}

      {/* Chats */}
      <div className="flex-1 overflow-y-auto scrollbar px-2 mt-3 pb-2">
        {pinned.length > 0 && (
          <>
            <p className="px-3 pt-1 pb-1 text-[10px] uppercase tracking-[0.14em] text-light-muted font-semibold">Pinned</p>
            {pinned.map((s) => <ChatRow key={s.id} s={s} />)}
          </>
        )}
        <p className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-[0.14em] text-light-muted font-semibold">Recents</p>
        {recents.length === 0
          ? <p className="px-3 py-3 text-[12px] text-light-muted">No chats yet.</p>
          : recents.map((s) => <ChatRow key={s.id} s={s} />)}
      </div>

      {/* Account + profile menu */}
      <div className="px-3 pt-2 mt-auto relative">
        {accountOpen && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setAccountOpen(false)} />
            <div className="absolute bottom-[58px] left-3 right-3 bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-xl shadow-xl p-1 z-50 fadeup">
              <button onClick={() => { onOpenSettings?.(); setAccountOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm hover:bg-surface-container-low dark:hover:bg-dark-bg text-left">
                <span className="material-symbols-outlined text-[18px] text-light-muted">settings</span>Settings
              </button>
              <button onClick={() => toggleTheme()}
                className="w-full flex items-center justify-between gap-2.5 px-3 py-2 rounded-lg text-sm hover:bg-surface-container-low dark:hover:bg-dark-bg text-left">
                <span className="flex items-center gap-2.5"><span className="material-symbols-outlined text-[18px] text-light-muted">dark_mode</span>Dark mode</span>
                <span className={`w-8 h-[18px] rounded-full relative transition ${dark ? "bg-accent-terracotta" : "bg-surface-container-highest dark:bg-dark-border"}`}>
                  <span className={`absolute top-0.5 left-0.5 w-3.5 h-3.5 rounded-full bg-white shadow-sm transition-transform ${dark ? "translate-x-[14px]" : ""}`} />
                </span>
              </button>
              {onLogout && (
                <>
                  <div className="h-px bg-light-border/60 dark:bg-dark-border my-1" />
                  <button onClick={() => { onLogout(); setAccountOpen(false); }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm hover:bg-surface-container-low dark:hover:bg-dark-bg text-left text-red-500">
                    <span className="material-symbols-outlined text-[18px]">logout</span>Log out
                  </button>
                </>
              )}
            </div>
          </>
        )}
        <button onClick={() => setAccountOpen((o) => !o)} aria-label="Account menu"
          className="w-full flex items-center gap-2.5 px-2 py-2 rounded-xl hover:bg-white/60 dark:hover:bg-dark-surface transition">
          <span className="w-8 h-8 rounded-lg bg-accent-terracotta text-white flex items-center justify-center text-[13px] font-semibold uppercase shrink-0">{display.charAt(0)}</span>
          <span className="flex-1 min-w-0 text-left">
            <span className="block text-[13px] font-semibold truncate">{display}</span>
            <span className="flex items-center gap-1.5 text-[10.5px] text-light-muted font-code">
              <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-emerald-500" : "bg-light-muted"}`} />
              {connected ? "Connected" : "Offline"} · ${today.toFixed(2)} today
            </span>
          </span>
          <span className="material-symbols-outlined text-[18px] text-light-muted">{accountOpen ? "expand_more" : "expand_less"}</span>
        </button>
      </div>
    </aside>
  );
}
