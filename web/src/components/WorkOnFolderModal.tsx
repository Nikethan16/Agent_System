import { useState, useEffect } from "react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";

// "Work on a folder" — pick a local folder; Nikki binds a project to it and opens a fresh
// chat there, so it reads & edits files directly in that folder (like Claude Code's cwd).
export default function WorkOnFolderModal({ onClose }: { onClose: () => void }) {
  const { createProject, setActiveProject, newSession } = useStore();
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = (path: string) => {
    setLoading(true); setErr("");
    api.browseLocal(path).then(setData).catch((e: any) => setErr(e?.message || String(e))).finally(() => setLoading(false));
  };
  useEffect(() => { load(""); }, []);

  const use = async () => {
    if (!data?.path || busy) return;
    setBusy(true);
    try {
      const name = data.path.split(/[\\/]/).filter(Boolean).pop() || "folder";
      const p = await createProject(name, "", "", data.path);
      await setActiveProject(p.id);
      await newSession();
      onClose();
    } catch (e: any) { setErr(e?.message || String(e)); setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 fadeup" onClick={onClose}>
      <div className="w-full max-w-md bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-2xl p-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 mb-1">
          <span className="material-symbols-outlined text-accent-terracotta text-[20px]">folder_open</span>
          <h2 className="font-semibold flex-1">Work on a folder</h2>
          <button onClick={onClose} aria-label="Close" className="material-symbols-outlined text-[18px] text-light-muted hover:text-on-surface dark:hover:text-dark-text">close</button>
        </div>
        <p className="text-[12px] text-light-muted mb-2">Pick a local folder — Nikki reads &amp; edits files directly in it.</p>
        <div className="border border-light-border dark:border-dark-border rounded-lg overflow-hidden bg-surface-container-low dark:bg-dark-bg">
          <div className="flex items-center gap-2 px-2 py-1.5 border-b border-light-border/60 dark:border-dark-border">
            <button type="button" disabled={!data?.parent} onClick={() => load(data.parent)} title="Up one folder"
              className="material-symbols-outlined text-[16px] text-light-muted hover:text-on-surface dark:hover:text-dark-text disabled:opacity-30">arrow_upward</button>
            <span className="font-code text-[11px] truncate flex-1 opacity-80">{data?.path || "…"}</span>
          </div>
          <div className="max-h-56 overflow-y-auto scrollbar">
            {loading && <div className="px-3 py-2 text-[12px] text-light-muted">Loading…</div>}
            {err && <div className="px-3 py-2 text-[12px] text-red-500">{err}</div>}
            {!loading && !err && data?.dirs?.length === 0 && <div className="px-3 py-2 text-[12px] text-light-muted">No subfolders here.</div>}
            {data?.dirs?.map((d: any) => (
              <button type="button" key={d.path} onClick={() => load(d.path)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-[12px] hover:bg-surface-container dark:hover:bg-dark-surface transition">
                <span className="material-symbols-outlined text-[15px] text-light-muted">folder</span>
                <span className="truncate flex-1">{d.name}</span>
                {d.is_repo && <span className="text-[9px] uppercase tracking-wide px-1 py-px rounded bg-emerald-500/12 text-emerald-600 dark:text-emerald-400">repo</span>}
              </button>
            ))}
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-3">
          <button onClick={onClose} className="text-[12px] px-3 py-1.5 rounded-lg text-light-muted hover:bg-surface-container-low dark:hover:bg-dark-bg">Cancel</button>
          <button onClick={use} disabled={!data?.path || busy}
            className="text-[12px] px-3 py-1.5 rounded-lg bg-accent-terracotta hover:bg-accent-deep text-white disabled:opacity-40">
            {busy ? "Opening…" : "Work on this folder"}
          </button>
        </div>
      </div>
    </div>
  );
}
