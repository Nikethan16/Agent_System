import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useStore } from "../lib/store";
import { api } from "../lib/api";

export default function ProjectModal({ pid, onClose }: { pid: string; onClose: () => void }) {
  const { projects, loadProjects, setActiveProject } = useStore();
  const proj = projects.find((p) => p.id === pid);
  const [instr, setInstr] = useState(proj?.instructions || "");
  const [files, setFiles] = useState<any[]>([]);
  const [repo, setRepo] = useState<any>(null);
  const reload = () => api.projectFiles(pid).then(setFiles);
  useEffect(() => {
    reload(); setInstr(proj?.instructions || "");
    api.projectRepo(pid).then(setRepo).catch(() => setRepo(null));
  }, [pid]);
  if (!proj) return null;
  const save = async () => { await api.updateProject(pid, { instructions: instr }); await loadProjects(); };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-6" onClick={onClose}>
      <div className="w-full max-w-lg bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-2xl p-6 max-h-[85vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display text-lg font-semibold">{proj.name}</h3>
          <button onClick={onClose} className="material-symbols-outlined text-light-muted hover:text-on-surface dark:hover:text-dark-text">close</button>
        </div>

        <label className="text-[11px] uppercase tracking-widest text-light-muted">Project instructions</label>
        <textarea value={instr} onChange={(e) => setInstr(e.target.value)} onBlur={save} rows={4}
          placeholder="Shared guidance/context injected into every chat in this project…"
          className="w-full mt-1 mb-5 bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg p-2.5 text-sm outline-none focus:border-accent-terracotta" />

        {repo?.repo && (
          <div className="mb-5 border border-light-border dark:border-dark-border rounded-xl p-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined text-[16px] text-accent-terracotta">account_tree</span>
              <span className="text-[13px] font-medium">{repo.branch}</span>
              <span className="text-[11px] text-light-muted">{repo.changed} uncommitted change{repo.changed === 1 ? "" : "s"}</span>
            </div>
            {repo.url && <div className="text-[10px] text-light-muted font-code truncate mb-2">{repo.url}</div>}
            {repo.recent?.length > 0 && (
              <div className="space-y-0.5">
                {repo.recent.map((c: string, i: number) => (
                  <div key={i} className="text-[11px] text-light-muted font-code truncate">{c}</div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex items-center justify-between mb-2">
          <label className="text-[11px] uppercase tracking-widest text-light-muted">Knowledge files</label>
          <label className="text-[11px] text-accent-terracotta cursor-pointer flex items-center gap-1 hover:brightness-110">
            <span className="material-symbols-outlined text-[14px]">upload</span> add
            <input type="file" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; if (f) { await api.addProjectFile(pid, f); reload(); e.currentTarget.value = ""; } }} />
          </label>
        </div>
        {files.length === 0 && <div className="text-light-muted text-xs mb-2">No files yet — uploads here are injected as context into every chat in this project.</div>}
        <div className="space-y-1">
          {files.map((f) => (
            <div key={f.name} className="flex items-center gap-2 text-sm border border-light-border dark:border-dark-border rounded-lg px-3 py-2">
              <span className="material-symbols-outlined text-[16px] text-accent-terracotta">description</span>
              <span className="flex-1 truncate">{f.name}</span>
              <span className="text-[10px] text-light-muted">{f.size}b</span>
              <span onClick={async () => { await api.removeProjectFile(pid, f.name); reload(); }} className="material-symbols-outlined text-[16px] text-light-muted hover:text-red-500 cursor-pointer">close</span>
            </div>
          ))}
        </div>

        <button onClick={async () => { if (confirm("Delete this project? Its chats stay but lose the shared context.")) { await api.deleteProject(pid); await loadProjects(); await setActiveProject(""); onClose(); } }}
          className="mt-6 text-[11px] uppercase tracking-wide text-red-500 hover:brightness-110">Delete project</button>
      </div>
    </div>,
    document.body,
  );
}
