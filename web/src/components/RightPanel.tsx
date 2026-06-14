import { useState } from "react";
import { useStore } from "../lib/store";
import FilesPanel from "./FilesPanel";
import CheckpointsPanel from "./CheckpointsPanel";
import JobsPanel from "./JobsPanel";
import SkillsPanel from "./SkillsPanel";

// Per-chat OUTPUT only. Configuration (Models, Memory) moved to Settings so this
// panel shows just what the agent produced for this conversation.
const TABS = [
  { id: "files", label: "Files" },
  { id: "checkpoints", label: "Rewind" },
  { id: "skills", label: "Skills" },
  { id: "tasks", label: "Tasks" },
];

export default function RightPanel({ open = false, onClose }: { open?: boolean; onClose?: () => void } = {}) {
  const [tab, setTab] = useState("files");
  const { files, jobs } = useStore();
  const count = (id: string): number | null => {
    if (id === "files" && files.length) return files.length;
    if (id === "tasks" && jobs.length) return jobs.length;
    return null;
  };
  return (
    <aside className={`fixed right-0 top-0 h-screen w-panel-width flex flex-col border-l border-light-border dark:border-dark-border bg-surface dark:bg-dark-surface z-40 transition-transform duration-200 ${open ? "translate-x-0" : "translate-x-full"}`}>
      <div className="flex items-center justify-between h-14 px-4 shrink-0">
        <span className="text-[13px] font-medium text-on-surface dark:text-dark-text">Artifacts</span>
        <button onClick={onClose} title="Close panel" aria-label="Close panel"
          className="p-1.5 rounded-lg text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg transition">
          <span className="material-symbols-outlined text-[18px]">close</span>
        </button>
      </div>
      <div className="flex border-b border-light-border dark:border-dark-border px-2">
        {TABS.map((t) => {
          const n = count(t.id);
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex-1 py-2.5 text-[11px] rounded-lg my-1 transition flex items-center justify-center gap-1 ${tab === t.id ? "bg-surface-container-high dark:bg-dark-bg text-on-surface dark:text-dark-text font-medium" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text"}`}>
              {t.label}
              {n != null && <span className="px-1 min-w-[15px] rounded-full bg-accent-terracotta/15 text-accent-terracotta text-[9px] font-bold leading-[15px]">{n}</span>}
            </button>
          );
        })}
      </div>
      <div className="flex-1 overflow-y-auto scrollbar min-h-0">
        {tab === "files" && <FilesPanel />}
        {tab === "checkpoints" && <CheckpointsPanel />}
        {tab === "skills" && <SkillsPanel />}
        {tab === "tasks" && <JobsPanel />}
      </div>
    </aside>
  );
}
