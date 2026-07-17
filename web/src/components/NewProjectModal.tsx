import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useStore } from "../lib/store";
import { api } from "../lib/api";

// Create a project — optionally FROM a Git repo, which clones it into the project's
// shared workspace so every session in the project works on the real code (OpenCode-style
// "open a repo"). Empty URL = a normal empty project.
export default function NewProjectModal({ onClose }: { onClose: () => void }) {
  const { createProject, localMode, localRoot } = useStore();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const nm = name.trim() || (url.trim() ? repoName(url) : "New project");
    setBusy(true);
    try {
      await createProject(nm, url.trim(), branch.trim(), localPath.trim());
      onClose();
    } finally {
      setBusy(false);
    }
  };

  const field = "w-full mt-1 bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent-terracotta transition";

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-6" onClick={onClose}>
      <div className="w-full max-w-md bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-2xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display text-lg font-semibold">New project</h3>
          <button onClick={onClose} aria-label="Close" className="material-symbols-outlined text-light-muted hover:text-on-surface dark:hover:text-dark-text">close</button>
        </div>

        <label className="text-[11px] uppercase tracking-widest text-light-muted">Name</label>
        <input autoFocus value={name} onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !busy) submit(); }}
          placeholder={url.trim() ? repoName(url) : "My project"} className={field} />

        <div className="mt-4">
          <label className="text-[11px] uppercase tracking-widest text-light-muted">Git repo URL <span className="normal-case tracking-normal">(optional)</span></label>
          <input value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/you/repo.git" className={field} />
          <p className="text-[11px] text-light-muted mt-1.5">
            Clones the repo into the project so every chat here works on it. Private repos need
            <code className="font-code mx-1">GITHUB_TOKEN</code>set on the server.
          </p>
        </div>

        {url.trim() && (
          <div className="mt-3">
            <label className="text-[11px] uppercase tracking-widest text-light-muted">Branch <span className="normal-case tracking-normal">(optional)</span></label>
            <input value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="default branch" className={field} />
          </div>
        )}

        {localMode && (
          <div className="mt-4 pt-4 border-t border-light-border/60 dark:border-dark-border">
            <label className="text-[11px] uppercase tracking-widest text-light-muted">Local folder <span className="normal-case tracking-normal">(edit in place)</span></label>
            <div className="flex gap-2 mt-1">
              <input value={localPath} onChange={(e) => setLocalPath(e.target.value)}
                placeholder={localRoot ? `${localRoot}${localRoot.includes("\\") ? "\\" : "/"}myrepo` : "/path/to/folder"}
                className={field + " flex-1 mt-0"} />
              <button type="button" onClick={() => setPicking((v) => !v)}
                className="shrink-0 flex items-center gap-1 px-3 rounded-lg border border-light-border dark:border-dark-border text-sm hover:border-accent-terracotta transition">
                <span className="material-symbols-outlined text-[16px]">folder_open</span>Browse
              </button>
            </div>
            {picking && <FolderPicker onPick={(p) => { setLocalPath(p); setPicking(false); }} />}
            <p className="text-[11px] text-light-muted mt-1.5">
              The agent edits these real files in place. Must be inside
              <code className="font-code mx-1">{localRoot || "your home folder"}</code>. Takes precedence over a Git URL.
            </p>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 mt-6">
          <button onClick={onClose} disabled={busy} className="px-3 py-2 text-sm text-light-muted hover:text-on-surface dark:hover:text-dark-text disabled:opacity-40">Cancel</button>
          <button onClick={submit} disabled={busy}
            className="px-4 py-2 text-sm rounded-lg bg-accent-terracotta hover:bg-accent-deep text-white flex items-center gap-2 disabled:opacity-50">
            {busy && <span className="material-symbols-outlined text-[16px] animate-spin">progressive_activity</span>}
            {busy ? (url.trim() ? "Cloning…" : "Creating…") : "Create"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

// "https://github.com/you/my-repo.git" -> "my-repo"
function repoName(url: string): string {
  const m = url.trim().replace(/\.git$/, "").match(/([^/]+)\/?$/);
  return m ? m[1] : "New project";
}

// Server-side directory navigator (works on the headless VM too, unlike a native OS
// dialog). Lists subfolders under AGENT_LOCAL_ROOT; click to descend, ↑ to go up (never
// above the root), "Use this folder" to pick the current directory.
function FolderPicker({ onPick }: { onPick: (path: string) => void }) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const load = (path: string) => {
    setLoading(true); setErr("");
    api.browseLocal(path)
      .then((d: any) => setData(d))
      .catch((e: any) => setErr(e?.message || String(e)))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(""); }, []);
  return (
    <div className="mt-2 border border-light-border dark:border-dark-border rounded-lg overflow-hidden bg-surface-container-low dark:bg-dark-bg">
      <div className="flex items-center gap-2 px-2 py-1.5 border-b border-light-border/60 dark:border-dark-border">
        <button type="button" disabled={!data?.parent} onClick={() => load(data.parent)} title="Up one folder"
          className="material-symbols-outlined text-[16px] text-light-muted hover:text-on-surface dark:hover:text-dark-text disabled:opacity-30">arrow_upward</button>
        <span className="font-code text-[11px] truncate flex-1 opacity-80">{data?.path || "…"}</span>
        <button type="button" onClick={() => data && onPick(data.path)}
          className="shrink-0 text-[11px] px-2 py-1 rounded bg-accent-terracotta hover:bg-accent-deep text-white">Use this folder</button>
      </div>
      <div className="max-h-48 overflow-y-auto">
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
  );
}
