import { useEffect, useState } from "react";
import { useStore } from "../lib/store";
import { api } from "../lib/api";

const money = (n?: number) => "$" + (n || 0).toFixed(2);

// The project's home page: overview + per-project usage/cost, its chats, files, and
// repo status. Opened from the sidebar's project ⋯ menu ("Project home").
export default function ProjectHome({ pid, onOpenSettings, onOpenChat }:
  { pid: string; onOpenSettings: () => void; onOpenChat: (id: string) => void }) {
  const { projects, sessions, selectSession } = useStore();
  const proj = projects.find((p: any) => p.id === pid);
  const [spend, setSpend] = useState<any>(null);
  const [files, setFiles] = useState<any[]>([]);
  const [repo, setRepo] = useState<any>(null);

  useEffect(() => {
    api.projectSpend(pid).then(setSpend).catch(() => setSpend(null));
    api.projectFiles(pid).then(setFiles).catch(() => setFiles([]));
    api.projectRepo(pid).then(setRepo).catch(() => setRepo(null));
  }, [pid]);

  const chats = sessions.filter((s: any) => s.project_id === pid)
    .sort((a: any, b: any) => Date.parse(b.updated_at || "") - Date.parse(a.updated_at || ""));

  if (!proj) return <div className="flex-1 grid place-items-center text-light-muted text-sm">Project not found.</div>;

  const cap = spend?.cap || spend?.budget_usd || 0;
  const spent = spend?.spent ?? spend?.spent_usd ?? 0;
  const pct = cap > 0 ? Math.min(100, (spent / cap) * 100) : 0;

  const Card = ({ children, className = "" }: { children: any; className?: string }) => (
    <div className={`border border-light-border dark:border-dark-border rounded-2xl bg-white dark:bg-dark-surface p-5 ${className}`}>{children}</div>
  );

  return (
    <div className="flex-1 overflow-y-auto scrollbar px-gutter py-8">
      <div className="max-w-[920px] mx-auto">
        {/* header */}
        <div className="flex items-center gap-3 mb-1">
          <span className="w-10 h-10 rounded-xl bg-accent-terracotta/12 text-accent-terracotta grid place-items-center shrink-0">
            <span className="material-symbols-outlined text-[22px]">folder</span>
          </span>
          <div className="flex-1 min-w-0">
            <h2 className="font-headline text-[24px] font-semibold tracking-tight truncate">{proj.name}</h2>
            <p className="text-[12px] text-light-muted">{chats.length} chat{chats.length === 1 ? "" : "s"} · {files.length} file{files.length === 1 ? "" : "s"}{repo?.repo && <> · {repo.branch}</>}</p>
          </div>
          <button onClick={onOpenSettings}
            className="shrink-0 flex items-center gap-2 px-3.5 py-2 rounded-xl border border-light-border dark:border-dark-border hover:border-accent-terracotta text-[13px] transition">
            <span className="material-symbols-outlined text-[17px]">settings</span> Settings
          </button>
        </div>
        {proj.instructions && <p className="text-[13px] text-on-surface-variant dark:text-light-muted mt-3 mb-6 max-w-[70ch]">{proj.instructions}</p>}
        {!proj.instructions && <div className="mb-6" />}

        {/* charts / stats */}
        <div className="grid sm:grid-cols-3 gap-3 mb-6">
          <Card>
            <p className="text-[11px] uppercase tracking-widest text-light-muted mb-1">Project spend</p>
            <div className="text-[24px] font-semibold tabular-nums">{money(spent)}</div>
            <div className="mt-3 h-2 rounded-full bg-surface-container-highest dark:bg-dark-border overflow-hidden">
              <div className="h-full rounded-full bg-accent-terracotta" style={{ width: `${pct}%` }} />
            </div>
            <p className="text-[11px] text-light-muted mt-1.5">{cap > 0 ? <>{money(cap - spent)} left of {money(cap)} cap</> : "No budget cap set"}</p>
          </Card>
          <Card>
            <p className="text-[11px] uppercase tracking-widest text-light-muted mb-1">Chats</p>
            <div className="text-[24px] font-semibold tabular-nums">{chats.length}</div>
            <p className="text-[11px] text-light-muted mt-3">Conversations sharing this project's workspace &amp; context.</p>
          </Card>
          <Card>
            <p className="text-[11px] uppercase tracking-widest text-light-muted mb-1">Repository</p>
            {repo?.repo ? (
              <>
                <div className="text-[15px] font-semibold flex items-center gap-1.5"><span className="material-symbols-outlined text-[18px] text-accent-terracotta">account_tree</span>{repo.branch}</div>
                <p className="text-[11px] text-light-muted mt-3">{repo.changed} uncommitted change{repo.changed === 1 ? "" : "s"}</p>
              </>
            ) : (
              <><div className="text-[15px] font-medium text-light-muted">Not a repo</div><p className="text-[11px] text-light-muted mt-3">Create the project from a Git URL to work on real code.</p></>
            )}
          </Card>
        </div>

        {/* chats */}
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <p className="text-[11px] uppercase tracking-widest text-light-muted font-semibold mb-2">Chats</p>
            <div className="space-y-1.5">
              {chats.length === 0 && <p className="text-[12px] text-light-muted">No chats in this project yet.</p>}
              {chats.map((s: any) => (
                <button key={s.id} onClick={() => { selectSession(s.id); onOpenChat(s.id); }}
                  className="w-full text-left flex items-center gap-2.5 border border-light-border dark:border-dark-border rounded-xl bg-white dark:bg-dark-surface px-3.5 py-2.5 hover:border-accent-terracotta transition">
                  <span className="material-symbols-outlined text-[17px] text-light-muted">chat_bubble</span>
                  <span className="flex-1 min-w-0 truncate text-[13px]">{s.title || "Untitled"}</span>
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-widest text-light-muted font-semibold mb-2">Files</p>
            <div className="space-y-1.5">
              {files.length === 0 && <p className="text-[12px] text-light-muted">No files yet.</p>}
              {files.map((f: any) => (
                <div key={f.name} className="flex items-center gap-2.5 border border-light-border dark:border-dark-border rounded-xl bg-white dark:bg-dark-surface px-3.5 py-2.5">
                  <span className="material-symbols-outlined text-[17px] text-accent-terracotta">description</span>
                  <span className="flex-1 min-w-0 truncate text-[13px]">{f.name}</span>
                  <span className="text-[10.5px] text-light-muted font-code">{f.size}b</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
