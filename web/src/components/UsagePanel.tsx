import { useEffect, useState } from "react";
import { api } from "../lib/api";

// Usage & Cost dashboard: today vs the daily cap, all-time total, a 14-day spend
// sparkbar series, and per-project spend (with caps). Reads /api/spend/overview.
type Day = { day: string; usd: number };
type Proj = { project_id: string; name: string; spent: number; cap: number | null };
type Overview = {
  spent_today: number; cap: number | null; remaining: number | null;
  all_time: number; history: Day[]; projects: Proj[];
};

const money = (n: number) => "$" + (n || 0).toFixed(n < 1 ? 4 : 2);

export default function UsagePanel() {
  const [d, setD] = useState<Overview | null>(null);
  const [err, setErr] = useState("");
  const load = () => api.spendOverview().then(setD).catch((e) => setErr(e.message || String(e)));
  useEffect(() => { load(); }, []);

  if (err) return <p className="text-sm text-red-500">Couldn’t load usage: {err}</p>;
  if (!d) return <p className="text-sm text-light-muted">Loading usage…</p>;

  const cap = d.cap ?? 0;
  const pct = cap > 0 ? Math.min(100, (d.spent_today / cap) * 100) : 0;
  const maxDay = Math.max(1e-9, ...d.history.map((h) => h.usd));
  const label = "text-[10px] uppercase tracking-widest text-light-muted mb-2";

  return (
    <div className="space-y-6">
      {/* top cards */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-light-border dark:border-dark-border p-3">
          <div className="text-[11px] text-light-muted">Spent today</div>
          <div className="text-2xl font-semibold mt-0.5">{money(d.spent_today)}</div>
          {cap > 0 ? (
            <>
              <div className="h-1.5 rounded-full bg-surface-container-high dark:bg-dark-bg mt-2 overflow-hidden">
                <div className={`h-full rounded-full ${pct > 90 ? "bg-red-500" : "bg-accent-terracotta"}`}
                     style={{ width: `${pct}%` }} />
              </div>
              <div className="text-[11px] text-light-muted mt-1">{money(d.remaining ?? 0)} left of {money(cap)} cap</div>
            </>
          ) : <div className="text-[11px] text-light-muted mt-2">No daily cap set</div>}
        </div>
        <div className="rounded-xl border border-light-border dark:border-dark-border p-3">
          <div className="text-[11px] text-light-muted">All-time total</div>
          <div className="text-2xl font-semibold mt-0.5">{money(d.all_time)}</div>
          <div className="text-[11px] text-light-muted mt-2">across all runs</div>
        </div>
      </div>

      {/* 14-day spend bars */}
      <div>
        <div className={label}>Daily spend (last {d.history.length} days)</div>
        <div className="flex items-end gap-1 h-24">
          {d.history.map((h) => (
            <div key={h.day} className="flex-1 flex flex-col items-center justify-end h-full group relative">
              <div className="w-full rounded-t bg-accent-terracotta/70 hover:bg-accent-terracotta transition-all min-h-[2px]"
                   style={{ height: `${(h.usd / maxDay) * 100}%` }} />
              <div className="absolute -top-6 hidden group-hover:block text-[10px] bg-on-surface text-white dark:bg-dark-text dark:text-dark-bg px-1.5 py-0.5 rounded whitespace-nowrap">
                {h.day.slice(5)}: {money(h.usd)}
              </div>
            </div>
          ))}
        </div>
        <div className="flex justify-between text-[10px] text-light-muted mt-1">
          <span>{d.history[0]?.day.slice(5)}</span>
          <span>today</span>
        </div>
      </div>

      {/* per-project spend */}
      <div>
        <div className={label}>Spend by project</div>
        {d.projects.length === 0 ? (
          <p className="text-xs text-light-muted">No project spend yet. Chats inside a Project are tracked here.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-[11px] text-light-muted">
              <tr><th className="text-left font-medium py-1">Project</th>
                  <th className="text-right font-medium py-1">Spent</th>
                  <th className="text-right font-medium py-1 pl-3">Budget</th></tr>
            </thead>
            <tbody>
              {d.projects.map((p) => (
                <tr key={p.project_id} className="border-t border-light-border dark:border-dark-border">
                  <td className="py-1.5 truncate max-w-[180px]">{p.name}</td>
                  <td className="py-1.5 text-right tabular-nums">{money(p.spent)}</td>
                  <td className="py-1.5 text-right pl-3 text-light-muted tabular-nums">
                    {p.cap ? money(p.cap) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <button onClick={load} className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border border-light-border dark:border-dark-border hover:bg-surface-container-low dark:hover:bg-dark-bg text-light-muted">
        <span className="material-symbols-outlined text-[15px]">refresh</span>Refresh
      </button>
    </div>
  );
}
