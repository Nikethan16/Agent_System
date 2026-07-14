import { useState } from "react";
import { useStore } from "../lib/store";
import FilesPanel from "./FilesPanel";
import CheckpointsPanel from "./CheckpointsPanel";
import JobsPanel from "./JobsPanel";
import SkillsPanel from "./SkillsPanel";
import TracesPanel from "./TracesPanel";

// Per-chat output. Default view is the WORKSPACE (project files + usage); the other
// views (Rewind/Skills/Tasks/Trace) live behind a discreet ⋯ menu so the panel stays
// clean but nothing is lost.
const VIEWS = [
  { id: "files", label: "Workspace", icon: "deployed_code" },
  { id: "checkpoints", label: "Rewind", icon: "history" },
  { id: "skills", label: "Skills", icon: "auto_awesome" },
  { id: "tasks", label: "Tasks", icon: "checklist" },
  { id: "trace", label: "Trace", icon: "account_tree" },
];

export default function RightPanel({ open = false, onClose }: { open?: boolean; onClose?: () => void } = {}) {
  const [view, setView] = useState("files");
  const [menu, setMenu] = useState(false);
  const { files, jobs, loadFiles, projects, activeProject } = useStore();
  const cur = VIEWS.find((v) => v.id === view)!;
  const projName = projects.find((p: any) => p.id === activeProject)?.name || "";
  const count = (id: string): number | null =>
    id === "files" ? (files.length || null) : id === "tasks" ? (jobs.length || null) : null;

  return (
    <aside className={`fixed right-0 top-0 h-screen w-full max-w-panel-width flex flex-col border-l border-light-border dark:border-dark-border bg-surface dark:bg-dark-surface z-40 transition-transform duration-200 ${open ? "translate-x-0" : "translate-x-full"}`}>
      <div className="flex items-center gap-2 h-14 px-4 shrink-0">
        <span className="material-symbols-outlined text-[18px] text-accent-terracotta">{cur.icon}</span>
        <span className="text-[13px] font-semibold text-on-surface dark:text-dark-text">{cur.label}</span>
        {view === "files" && projName && (
          <span className="text-[11px] text-light-muted font-code flex items-center gap-1 truncate ml-1">
            <span className="material-symbols-outlined text-[13px]">star</span>{projName}
          </span>
        )}
        <div className="ml-auto flex items-center gap-0.5">
          {view === "files" && (
            <button onClick={() => loadFiles()} title="Refresh"
              className="p-1.5 rounded-lg text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg transition">
              <span className="material-symbols-outlined text-[17px]">refresh</span>
            </button>
          )}
          <div className="relative">
            <button onClick={() => setMenu((o) => !o)} title="Panels" aria-label="More panels"
              className={`p-1.5 rounded-lg transition ${menu ? "bg-surface-container-low dark:bg-dark-bg text-on-surface dark:text-dark-text" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg"}`}>
              <span className="material-symbols-outlined text-[18px]">more_horiz</span>
            </button>
            {menu && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setMenu(false)} />
                <div className="absolute right-0 top-full mt-1 w-44 bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-xl shadow-xl p-1 z-50 fadeup">
                  {VIEWS.map((v) => {
                    const n = count(v.id);
                    return (
                      <button key={v.id} onClick={() => { setView(v.id); setMenu(false); }}
                        className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] text-left transition ${view === v.id ? "bg-surface-container-low dark:bg-dark-bg font-semibold" : "hover:bg-surface-container-low dark:hover:bg-dark-bg"}`}>
                        <span className="material-symbols-outlined text-[17px] text-light-muted">{v.icon}</span>{v.label}
                        {n != null && <span className="ml-auto text-[10px] font-code text-light-muted">{n}</span>}
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </div>
          <button onClick={onClose} title="Close panel" aria-label="Close panel"
            className="p-1.5 rounded-lg text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg transition">
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar min-h-0 border-t border-light-border dark:border-dark-border">
        {view === "files" && <FilesPanel />}
        {view === "checkpoints" && <CheckpointsPanel />}
        {view === "skills" && <SkillsPanel />}
        {view === "tasks" && <JobsPanel />}
        {view === "trace" && <TracesPanel />}
      </div>
    </aside>
  );
}
