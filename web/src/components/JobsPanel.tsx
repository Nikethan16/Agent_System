import { useEffect } from "react";
import { useStore } from "../lib/store";

const COLOR: Record<string, string> = {
  queued: "bg-amber-100 text-amber-700",
  running: "bg-blue-100 text-blue-700",
  done: "bg-emerald-100 text-emerald-700",
  error: "bg-red-100 text-red-700",
};

export default function JobsPanel() {
  const { jobs, loadJobs } = useStore();
  useEffect(() => {
    loadJobs();
    const t = setInterval(loadJobs, 3000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="p-5">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-[11px] uppercase tracking-widest text-light-muted">Background tasks</h4>
        <button onClick={() => loadJobs()} className="text-light-muted hover:text-on-surface dark:hover:text-dark-text">
          <span className="material-symbols-outlined text-[18px]">refresh</span>
        </button>
      </div>
      {jobs.length === 0 && (
        <div className="text-light-muted text-xs">No background tasks. Use the <span className="material-symbols-outlined text-[14px]">schedule</span> button in the composer to queue one (runs unattended).</div>
      )}
      <div className="space-y-2">
        {jobs.map((j) => (
          <div key={j.id} className="border border-light-border dark:border-dark-border rounded-xl p-3 bg-white dark:bg-dark-surface">
            <div className="flex items-center gap-2 mb-1">
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${COLOR[j.status] || "bg-surface-container text-on-surface-variant"}`}>{j.status}</span>
            </div>
            <p className="text-sm truncate">{j.text}</p>
            {j.result && <p className="text-[11px] text-light-muted mt-1 line-clamp-2">{j.result}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}
