import { useState, type MouseEvent } from "react";
import { createPortal } from "react-dom";
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
          connected, spend, folders, createFolder, renameFolder, deleteFolder, moveSession } = useStore();
  const [newProj, setNewProj] = useState(false);
  const [settingsPid, setSettingsPid] = useState<string | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const [projOpen, setProjOpen] = useState(true);         // Projects section expanded
  const [openProj, setOpenProj] = useState<string | null>(null);  // which project shows its chats
  const [openFolder, setOpenFolder] = useState<string | null>(null);  // which folder shows its chats
  const [projMenu, setProjMenu] = useState<string | null>(null);  // which project's ⋯ menu is open
  const [folderMenu, setFolderMenu] = useState<string | null>(null);  // which folder's ⋯ menu is open
  const [nav, setNav] = useState<"chat" | "scheduled">("chat");
  const dark = theme === "dark";
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  // Per-chat ⋯ menu — fixed-positioned so it isn't clipped by the scrolling chat list.
  const [chatMenu, setChatMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [moveMode, setMoveMode] = useState(false);   // chat menu showing "Move to…" targets
  const commit = (id: string) => { if (draft.trim()) renameSession(id, draft.trim()); setEditing(null); };

  const goChat = () => { setNav("chat"); onGoChat?.(); };
  const byUpdated = (a: any, b: any) => Date.parse(b.updated_at || "") - Date.parse(a.updated_at || "");
  const pinned = sessions.filter((s) => s.starred && !s.project_id).sort(byUpdated);
  const recents = sessions.filter((s) => !s.starred && !s.project_id).sort(byUpdated);
  const projFolders = (pid: string) => folders.filter((f: any) => f.project_id === pid)
    .sort((a: any, b: any) => (a.name || "").localeCompare(b.name || ""));
  const folderChats = (fid: string) => sessions.filter((s) => s.folder_id === fid).sort(byUpdated);
  const projLooseChats = (pid: string) => sessions.filter((s) => s.project_id === pid && !s.folder_id).sort(byUpdated);

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
  const addFolder = async (pid: string) => {
    const n = prompt("New folder name", "New folder"); setProjMenu(null);
    if (n && n.trim()) { const f = await createFolder(pid, n.trim()); setOpenProj(pid); setOpenFolder(f?.id || null); }
  };
  const editFolder = async (fid: string, cur: string) => {
    const n = prompt("Rename folder", cur); setFolderMenu(null);
    if (n && n.trim()) await renameFolder(fid, n.trim());
  };
  const removeFolder = async (fid: string) => {
    setFolderMenu(null);
    if (confirm("Delete this folder? Its chats move back to the project.")) await deleteFolder(fid);
  };

  const openChatMenu = (e: MouseEvent, id: string) => {
    e.stopPropagation();
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setChatMenu({ id, x: Math.min(r.left - 180, window.innerWidth - 236), y: Math.min(r.bottom + 4, window.innerHeight - 240) });
    setMoveMode(false);
  };
  const doMove = async (pid: string | null, fid: string | null) => {
    if (chatMenu) await moveSession(chatMenu.id, pid, fid);
    setChatMenu(null); setMoveMode(false);
  };
  const menuChat = chatMenu ? sessions.find((s) => s.id === chatMenu.id) : null;

  const NavBtn = ({ id, icon, label, onClick }: { id: string; icon: string; label: string; onClick: () => void }) => (
    <button onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] transition ${nav === id
        ? "bg-accent-terracotta/12 text-accent-deep dark:text-accent-terracotta font-semibold"
        : "text-on-surface-variant dark:text-light-muted hover:bg-white/60 dark:hover:bg-dark-surface hover:text-on-surface dark:hover:text-dark-text"}`}>
      <span className="material-symbols-outlined text-[19px]">{icon}</span>{label}
    </button>
  );

  const ChatRow = ({ s, indent, pad }: { s: any; indent?: boolean; pad?: string }) => (
    <div role="button" tabIndex={0}
      onClick={() => { selectSession(s.id); goChat(); onClose?.(); }}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectSession(s.id); goChat(); onClose?.(); } }}
      className={`group flex items-center gap-2.5 ${pad ?? (indent ? "pl-9" : "pl-3")} pr-2 py-1.5 rounded-lg cursor-pointer transition ${s.id === currentId ? "bg-white dark:bg-dark-surface shadow-sm" : "hover:bg-white/60 dark:hover:bg-dark-surface/60"}`}>
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
      {s.starred && (
        <span className="material-symbols-outlined text-[14px] shrink-0 text-accent-terracotta" title="Pinned"
          style={{ fontVariationSettings: "'FILL' 1" }}>star</span>
      )}
      <button title="Chat options" onClick={(e) => openChatMenu(e, s.id)}
        className="material-symbols-outlined text-[17px] shrink-0 opacity-0 group-hover:opacity-100 text-light-muted hover:text-on-surface dark:hover:text-dark-text px-0.5">more_horiz</button>
    </div>
  );

  const MenuItem = ({ icon, label, onClick, danger }: { icon: string; label: string; onClick: () => void; danger?: boolean }) => (
    <button onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] hover:bg-surface-container-low dark:hover:bg-dark-bg text-left ${danger ? "text-red-500" : ""}`}>
      <span className={`material-symbols-outlined text-[16px] ${danger ? "" : "text-light-muted"}`}>{icon}</span>{label}
    </button>
  );

  return (
    <aside className={`fixed left-0 top-0 h-screen w-sidebar-width max-w-[85vw] flex flex-col bg-claude-sidebar dark:bg-claude-sidebar-dark py-4 z-40 transition-transform duration-200 md:translate-x-0 md:max-w-none ${open ? "translate-x-0" : "-translate-x-full"}`}>
      <div className="px-4 mb-3 flex items-center gap-2.5">
        <Sunburst size={26} />
        <h1 className="font-headline text-[15px] font-semibold tracking-tight leading-none">Nikki</h1>
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
              const pFolders = projFolders(p.id);
              const loose = projLooseChats(p.id);
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
                            <MenuItem icon="dashboard" label="Project home" onClick={() => { setActiveProject(p.id); onOpenProject?.(p.id); setProjMenu(null); onClose?.(); }} />
                            <MenuItem icon="create_new_folder" label="New folder" onClick={() => addFolder(p.id)} />
                            <MenuItem icon="settings" label="Project settings" onClick={() => { setSettingsPid(p.id); setProjMenu(null); }} />
                            <MenuItem icon="edit" label="Rename" onClick={() => renameProject(p.id, p.name)} />
                            <div className="h-px bg-light-border/60 dark:bg-dark-border my-1" />
                            <MenuItem icon="delete" label="Delete" danger onClick={() => removeProject(p.id)} />
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                  {isOpen && (
                    <div className="mt-0.5 mb-1">
                      {pFolders.map((f: any) => {
                        const fOpen = openFolder === f.id;
                        const chats = folderChats(f.id);
                        return (
                          <div key={f.id}>
                            <div className="group flex items-center gap-2 pl-7 pr-1.5 py-1.5 rounded-lg cursor-pointer transition hover:bg-white/60 dark:hover:bg-dark-surface/60"
                              onClick={() => setOpenFolder(fOpen ? null : f.id)}>
                              <span className={`material-symbols-outlined text-[14px] text-light-muted shrink-0 transition-transform ${fOpen ? "" : "-rotate-90"}`}>expand_more</span>
                              <span className="material-symbols-outlined text-[15px] text-light-muted shrink-0">folder_open</span>
                              <span className="flex-1 min-w-0 truncate text-[12.5px] font-medium text-on-surface-variant dark:text-light-muted">{f.name}</span>
                              {chats.length > 0 && <span className="text-[10px] text-light-muted font-code shrink-0">{chats.length}</span>}
                              <div className="relative shrink-0">
                                <button onClick={(e) => { e.stopPropagation(); setFolderMenu(folderMenu === f.id ? null : f.id); }}
                                  title="Folder options"
                                  className="material-symbols-outlined text-[16px] text-light-muted opacity-0 group-hover:opacity-100 hover:text-on-surface dark:hover:text-dark-text px-0.5">more_horiz</button>
                                {folderMenu === f.id && (
                                  <>
                                    <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); setFolderMenu(null); }} />
                                    <div className="absolute right-0 top-full mt-1 w-40 bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-xl shadow-xl p-1 z-50 fadeup" onClick={(e) => e.stopPropagation()}>
                                      <MenuItem icon="edit" label="Rename" onClick={() => editFolder(f.id, f.name)} />
                                      <MenuItem icon="delete" label="Delete" danger onClick={() => removeFolder(f.id)} />
                                    </div>
                                  </>
                                )}
                              </div>
                            </div>
                            {fOpen && (chats.length === 0
                              ? <p className="pl-[52px] py-1 text-[12px] text-light-muted">Empty — move chats here.</p>
                              : chats.map((s: any) => <ChatRow key={s.id} s={s} indent pad="pl-[52px]" />))}
                          </div>
                        );
                      })}
                      {loose.length === 0 && pFolders.length === 0
                        ? <p className="pl-9 py-1 text-[12px] text-light-muted">No chats in this project.</p>
                        : loose.slice(0, 12).map((s: any) => <ChatRow key={s.id} s={s} indent />)}
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

      {/* per-chat ⋯ menu — portaled to <body> so the sidebar's transform doesn't
          re-anchor its fixed position, and so it can't be clipped by the scroll list. */}
      {chatMenu && menuChat && createPortal(
        <>
          <div className="fixed inset-0 z-40" onClick={() => { setChatMenu(null); setMoveMode(false); }} />
          <div className="fixed z-50 w-56 max-h-[60vh] overflow-y-auto scrollbar bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-xl shadow-xl p-1 fadeup"
            style={{ left: chatMenu.x, top: chatMenu.y }} onClick={(e) => e.stopPropagation()}>
            {!moveMode ? (
              <>
                <MenuItem icon="edit" label="Rename" onClick={() => { setEditing(menuChat.id); setDraft(menuChat.title || ""); setChatMenu(null); }} />
                <MenuItem icon="push_pin" label={menuChat.starred ? "Unpin" : "Pin"} onClick={() => { toggleStar(menuChat.id); setChatMenu(null); }} />
                <MenuItem icon="drive_file_move" label="Move to…" onClick={() => setMoveMode(true)} />
                <div className="h-px bg-light-border/60 dark:bg-dark-border my-1" />
                <MenuItem icon="delete" label="Delete" danger onClick={() => { if (confirm("Delete this chat and its files?")) deleteSession(menuChat.id); setChatMenu(null); }} />
              </>
            ) : (
              <>
                <button onClick={() => setMoveMode(false)}
                  className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12px] text-light-muted hover:bg-surface-container-low dark:hover:bg-dark-bg text-left">
                  <span className="material-symbols-outlined text-[15px]">arrow_back</span>Move to
                </button>
                <div className="h-px bg-light-border/60 dark:bg-dark-border my-1" />
                <MenuItem icon="chat_bubble" label="Chats (no project)" onClick={() => doMove("", "")} />
                {projects.length === 0 && <p className="px-3 py-1 text-[12px] text-light-muted">No projects yet.</p>}
                {projects.map((p: any) => (
                  <div key={p.id}>
                    <MenuItem icon="folder" label={p.name} onClick={() => doMove(p.id, "")} />
                    {projFolders(p.id).map((f: any) => (
                      <button key={f.id} onClick={() => doMove(p.id, f.id)}
                        className="w-full flex items-center gap-2.5 pl-8 pr-3 py-1.5 rounded-lg text-[12.5px] hover:bg-surface-container-low dark:hover:bg-dark-bg text-left text-on-surface-variant dark:text-light-muted">
                        <span className="material-symbols-outlined text-[15px] text-light-muted">folder_open</span>{f.name}
                      </button>
                    ))}
                  </div>
                ))}
              </>
            )}
          </div>
        </>,
        document.body,
      )}

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
