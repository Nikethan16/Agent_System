import { useState } from "react";
import FilesPanel from "./FilesPanel";
import CheckpointsPanel from "./CheckpointsPanel";
import ModelRail from "./ModelRail";
import JobsPanel from "./JobsPanel";
import SkillsPanel from "./SkillsPanel";
import MemoryPanel from "./MemoryPanel";

const TABS = [
  { id: "files", label: "Files" },
  { id: "checkpoints", label: "Rewind" },
  { id: "memory", label: "Memory" },
  { id: "skills", label: "Skills" },
  { id: "tasks", label: "Tasks" },
  { id: "models", label: "Models" },
];

export default function RightPanel({ open = false, onClose }: { open?: boolean; onClose?: () => void } = {}) {
  const [tab, setTab] = useState("files");
  return (
    <aside className={`fixed right-0 top-0 h-screen w-panel-width flex flex-col border-l border-light-border dark:border-dark-border bg-surface dark:bg-dark-surface z-40 transition-transform duration-200 md:translate-x-0 ${open ? "translate-x-0" : "translate-x-full"}`}>
      <button onClick={onClose} title="Close"
        className="md:hidden absolute -left-10 top-3 bg-surface dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-l-lg p-1.5 text-light-muted">
        <span className="material-symbols-outlined text-[18px]">close</span>
      </button>
      <div className="flex border-b border-light-border dark:border-dark-border">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex-1 py-4 text-[10px] uppercase tracking-wide border-b-2 transition ${tab === t.id ? "text-primary dark:text-accent-terracotta border-accent-terracotta font-bold" : "text-light-muted border-transparent hover:text-on-surface dark:hover:text-dark-text"}`}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto scrollbar min-h-0">
        {tab === "files" && <FilesPanel />}
        {tab === "checkpoints" && <CheckpointsPanel />}
        {tab === "memory" && <MemoryPanel />}
        {tab === "skills" && <SkillsPanel />}
        {tab === "tasks" && <JobsPanel />}
        {tab === "models" && <ModelRail />}
      </div>
    </aside>
  );
}
