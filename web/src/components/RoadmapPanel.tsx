import { useEffect, useState } from "react";
import { useStore } from "../lib/store";
import { api } from "../lib/api";

// Settings → Roadmap: the agent's resumable Project State for this chat/project
// (what's done, what's next) — the thing that lets a new chat continue the work.
export default function RoadmapPanel() {
  const currentId = useStore((s) => s.currentId);
  const [st, setSt] = useState<any>(null);

  const load = async () => {
    if (!currentId) return;
    try { setSt(await api.state(currentId)); } catch { /* empty */ }
  };
  useEffect(() => { load(); }, [currentId]);

  if (!currentId) return <div className="text-xs text-light-muted">Open a chat to see its roadmap.</div>;
  const plan = (st && st.plan) || [];
  const mark = (s: string) => (s === "done" ? "✓" : s === "in_progress" ? "◐" : "○");

  return (
    <div className="space-y-3">
      <div className="text-[11px] text-light-muted">
        The agent's resumable roadmap for this chat/project — work picks up here next time, even in a new chat.
      </div>
      {st && st.goal && <div className="text-sm"><b>Goal:</b> {st.goal}</div>}
      {(!st || !plan.length) && <div className="text-xs text-light-muted">No roadmap yet — it appears after a multi-step task.</div>}
      {plan.map((t: any, i: number) => (
        <div key={i} className="flex items-center gap-2 text-sm">
          <span className={t.status === "done" ? "text-emerald-600" : "text-light-muted"}>{mark(t.status)}</span>
          <span className={t.status === "done" ? "line-through text-light-muted" : ""}>{t.text}</span>
        </div>
      ))}
      {st && st.next && <div className="text-xs text-accent-terracotta">Next: {st.next}</div>}
      {st && (st.artifacts || []).length > 0 && (
        <div className="text-[11px] text-light-muted">Files: {st.artifacts.join(", ")}</div>
      )}
      {st && plan.length > 0 && (
        <button onClick={async () => { await api.clearState(currentId); setSt(null); }}
          className="text-[11px] text-light-muted hover:text-red-500">clear roadmap</button>
      )}
    </div>
  );
}
