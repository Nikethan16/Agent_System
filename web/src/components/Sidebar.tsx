import { useState } from "react";
import { useStore } from "../lib/store";
import { api } from "../lib/api";
import ProjectModal from "./ProjectModal";
import NewProjectModal from "./NewProjectModal";
import Sunburst from "./Sunburst";

export default function Sidebar({ open = false, onClose, email = "", onOpenSettings, onLogout,
  onOpenSearch, onOpenScheduled, onGoChat, onOpenProject }:
  { open?: boolean; onClose?: () => void; email?: string; onOpenSettings?: () => void;
    onLogout?: () => void; onOpenSearch?: () => void; onOpenScheduled?: () => void;
    onGoChat?: () => void; onOpenProject?: (pid: string) => void } = {}) {
  const { sessions, currentId, newSession, selectSession, deleteSession, renameSession,
          projects, activeProject, setActiveProject, loadProjects, toggleStar, theme, toggleTheme,
          connected, spend } = useStore();
  const [newProj, setNewProj] = useState(false);
  const [settingsPid, setSettingsPid] = useState<string | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const [projOpen, setProjOpen] = useState(true);         // Projects section expanded
  const [openProj, setOpenProj] = useState<string | null>(null);  // which project shows its chats
  const [projMenu, setProjMenu] = useState<string | null>(null);  // which project's ⋯ menu is open
  const [nav, setNav] = useState<"chat" | "scheduled">("chat");
  const dark = theme === "dark";
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const commit = (id: string) => { if (draft.trim()) renameSession(id, draft.trim()); setEditing(null); };

  const goChat = () => { setNav("chat"); onGoChat?.(); };
  const pinned = sessions.filter((s) => s.starred && !s.project_id)
    .sort((a, b) => Date.parse(b.updated_at || "") - Date.parse(a.updated_at || ""));
  const recents = sessions.filter((s) => !s.starred && !s.project_id)
    .sort((a, b) => Date.parse(b.updated_at || "") - Date.parse(a.updated_at || ""));
  const projChats = (pid: string) => sessions.filter((s) => s.project_id === pid)
    .sort((a, b) => Date.parse(b.updated_at || "") - Date.parse(a.updated_at || ""));

  const name = ((email.split("@")[0] || "").replace(/[0-9._-]+$/, "") || "Account");
  const display = name.charAt(0).toUpperCase() + name.slice(1);
  const today = spend?.spent_today || 0;

  const removeProject = async (pid: string) => {
    if (!confirm("Delete this project? Its chats stay but lose the shared context.")) return;
    await api.deleteProject(pid); await loadProjects();
    if (activeProject === pid) setActiveProject("");
    setProjMenu(null);
  };
  const renameProject = async (pid: string, cur: string) => {
    const n = prompt("Rename project", cur); setProjMenu(null);
    if (n && n.trim()) { await api.updateProject(pid, { name: n.trim() }); await loadProjects(); }
  };

  const NavBtn = ({ id, icon, label, onClick }: { id: string; icon: string; label: string; onClick: () => void }) => (
    <button onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] transition ${nav === id
        ? "bg-accent-terracotta/12 text-accent-deep dark:text-accent-terracotta font-semibold"
        : "text-on-surface-variant dark:text-light-muted hover:bg-white/60 dark:hover:bg-dark-surface hover:text-on-surface dark:hover:text-dark-text"}`}>
      <span className="material-symbols-outlined text-[19px]">{icon}</span>{label}
    </button>
  );

  const ChatRow = ({ s, indent }: { s: any; indent?: boolean }) => (
    <div role="button" tabIndex={0}
      onClick={() => { selectSession(s.id); goChat(); onClose?.(); }}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectSession(s.id); goChat(); onClose?.(); } }}
      className={`group flex items-center gap-2.5 ${indent ? "pl-9" : "pl-3"} pr-2 py-1.5 rounded-lg cursor-pointer transition ${s.id === currentId ? "bg-white dark:bg-dark-surface shadow-sm" : "hover:bg-white/60 dark:hover:bg-dark-surface/60"}`}>
      {!indent && <span className="material-symbols-outlined text-[16px] text-light-muted shrink-0">chat_bubble</span>}
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
      <span role="button" tabIndex={0} title="Star" onClick={(e) => { e.stopPropagation(); toggleStar(s.id); }}
        className={`material-symbols-outlined text-[15px] shrink-0 ${s.starred ? "text-accent-terracotta opacity-100" : "text-light-muted opacity-0 group-hover:opacity-100 hover:text-accent-terracotta"}`}
        style={s.starred ? { fontVariationSettings: "'FILL' 1" } : undefined}>star</span>
      <span role="button" tabIndex={0} title="Delete" onClick={(e) => { e.stopPropagation(); if (confirm("Delete this chat and its files?")) deleteSession(s.id); }}
        className="material-symbols-outlined text-[16px] shrink-0 opacity-0 group-hover:opacity-100 text-light-muted hover:text-red-500">close</span>
    </div>
  );

  return (
    <aside className={`fixed left-0 top-0 h-screen w-sidebar-width max-w-[85vw] flex flex-col bg-claude-sidebar dark:bg-claude-sidebar-dark py-4 z-40 transition-transform duration-200 md:translate-x-0 md:max-w-none ${open ? "translate-x-0" : "-translate-x-full"}`}>
      <div className="px-4 mb-3 flex items-center gap-2.5">
        <Sunburst size={26} />
        <h1 className="font-headline text-[15px] font-semibold tracking-tight leading-none">AGENT <span className="text-accent-terracotta">//</span> CORE</h1>
      </div>

      {/* primary nav */}
      <nav className="px-3 flex flex-col gap-0.5">
        <button onClick={() => { newSession(); goChat(); onClose?.(); }}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium text-accent-deep dark:text-accent-terracotta hover:bg-white/60 dark:hover:bg-dark-surface transition">
          <span className="material-symbols-outlined text-[19px]">edit_square</span> New chat
        </button>
        <NavBtn id="search" icon="search" label="Search" onClick={() => onOpenSearch?.()} />
        <NavBtn id="scheduled" icon="schedule" label="Scheduled" onClick={() => { setNav("scheduled"); onOpenScheduled?.(); }} />
      </nav>

      {/* Projects — expandable section */}
      <div className="px-3 mt-3">
        <div className="flex items-center gap-1 px-2">
          <button onClick={() => setProjOpen((o) => !o)}
            className="flex items-center gap-1 flex-1 text-[10px] uppercase tracking-[0.14em] text-light-muted font-semibold py-1">
            <span className={`material-symbols-outlined text-[14px] transition-transform ${projOpen ? "" : "-rotate-90"}`}>expand_more</span>
            Projects
          </button>
          <button onClick={() => setNewProj(true)} title="New project"
            className="p-1 rounded-md text-light-muted hover:text-accent-deep dark:hover:text-accent-terracotta hover:bg-white/60 dark:hover:bg-dark-surface">
            <span className="material-symbols-outlined text-[16px]">add</span>
          </button>
        </div>
        {projOpen && (
          <div className="mt-0.5">
            {projects.length === 0 && <p className="px-3 py-1 text-[12px] text-light-muted">No projects yet.</p>}
            {projects.map((p: any) => {
              const isOpen = openProj === p.id;
              return (
                <div key={p.id}>
                  <div className={`group flex items-center gap-2 pl-3 pr-1.5 py-1.5 rounded-lg cursor-pointer transition ${activeProject === p.id ? "bg-white dark:bg-dark-surface shadow-sm" : "hover:bg-white/60 dark:hover:bg-dark-surface/60"}`}
                    onClick={() => { setActiveProject(p.id); setOpenProj(isOpen ? null : p.id); }}>
                    <span className="material-symbols-outlined text-[16px] text-accent-terracotta shrink-0">folder</span>
                    <span className="flex-1 min-w-0 truncate text-[13px] font-medium">{p.name}</span>
                    <div className="relative shrink-0">
                      <button onClick={(e) => { e.stopPropagation(); setProjMenu(projMenu === p.id ? null : p.id); }}
                        title="Project options"
                        className="material-symbols-outlined text-[17px] text-light-muted opacity-0 group-hover:opacity-100 hover:text-on-surface dark:hover:text-dark-text px-0.5">more_horiz</button>
                      {projMenu === p.id && (
                        <>
                          <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); setProjMenu(null); }} />
                          <div className="absolute right-0 top-full mt-1 w-44 bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-xl shadow-xl p-1 z-50 fadeup" onClick={(e) => e.stopPropagation()}>
                            <button onClick={() => { setActiveProject(p.id); onOpenProject?.(p.id); setProjMenu(null); onClose?.(); }} className="w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] hover:bg-surface-container-low dark:hover:bg-dark-bg text-left"><span className="material-symbols-outlined text-[16px] text-light-muted">dashboard</span>Project home</button>
                            <button onClick={() => { setSettingsPid(p.id); setProjMenu(null); }} className="w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] hover:bg-surface-container-low dark:hover:bg-dark-bg text-left"><span className="material-symbols-outlined text-[16px] text-light-muted">settings</span>Project settings</button>
                            <button onClick={() => renameProject(p.id, p.name)} className="w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] hover:bg-surface-container-low dark:hover:bg-dark-bg text-left"><span className="material-symbols-outlined text-[16px] text-light-muted">edit</span>Rename</button>
                            <div className="h-px bg-light-border/60 dark:bg-dark-border my-1" />
                            <button onClick={() => removeProject(p.id)} className="w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] hover:bg-surface-container-low dark:hover:bg-dark-bg text-left text-red-500"><span className="material-symbols-outlined text-[16px]">delete</span>Delete</button>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                  {isOpen && (
                    <div className="mt-0.5 mb-1">
                      {projChats(p.id).length === 0
                        ? <p className="pl-9 py-1 text-[12px] text-light-muted">No chats in this project.</p>
                        : projChats(p.id).slice(0, 6).map((s: any) => <ChatRow key={s.id} s={s} indent />)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {settingsPid && <ProjectModal pid={settingsPid} onClose={() => setSettingsPid(null)} />}
      {newProj && <NewProjectModal onClose={() => setNewProj(false)} />}

      {/* chats */}
      <div className="flex-1 overflow-y-auto scrollbar px-2 mt-3 pb-2">
        {pinned.length > 0 && (
          <>
            <p className="px-3 pt-1 pb-1 text-[10px] uppercase tracking-[0.14em] text-light-muted font-semibold">Pinned</p>
            {pinned.map((s) => <ChatRow key={s.id} s={s} />)}
          </>
        )}
        <p className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-[0.14em] text-light-muted font-semibold">Chats</p>
        {recents.length === 0
          ? <p className="px-3 py-3 text-[12px] text-light-muted">No chats yet.</p>
          : recents.map((s) => <ChatRow key={s.id} s={s} />)}
      </div>

      {/* account + profile menu */}
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
