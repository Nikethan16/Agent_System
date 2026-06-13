import { useEffect, useState } from "react";
import { api } from "../lib/api";

// Model Health: per-model call metrics (latency / errors / fallbacks / cost), per-key
// pool usage, and cache hit-rates. This is the call-level view the event feed lacked —
// it answers "which models are slow / erroring / getting fallen-back-from?" for tuning
// the multi-key NVIDIA fleet, and shows how much the caches are saving.
type Health = {
  keys: Record<string, any[]>;
  models: any[];
  recent: any[];
  caches: Record<string, any>;
};

const shortModel = (m: string) => (m || "").split("/").slice(-1)[0] || m;

function Bar({ label, children }: { label: string; children?: any }) {
  return (
    <div className="flex items-center justify-between text-[11px] py-0.5">
      <span className="text-light-muted truncate mr-2">{label}</span>
      <span className="font-code">{children}</span>
    </div>
  );
}

export default function HealthPanel() {
  const [data, setData] = useState<Health | null>(null);
  const [err, setErr] = useState("");

  const load = () => api.fleetHealth().then(setData).catch((e) => setErr(e.message || String(e)));
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);   // live-ish refresh while the panel is open
    return () => clearInterval(t);
  }, []);

  const reset = () => api.resetHealth().then(load);

  if (err) return <div className="text-xs text-red-500">Couldn't load health: {err}</div>;
  if (!data) return <div className="text-xs text-light-muted">Loading…</div>;

  const models = data.models || [];
  const caches = Object.entries(data.caches || {});
  const keyProviders = Object.entries(data.keys || {});

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">Model health</div>
        <button onClick={reset} className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg border border-light-border dark:border-dark-border hover:bg-surface-container-low dark:hover:bg-dark-bg">
          <span className="material-symbols-outlined text-[14px]">restart_alt</span>Reset metrics
        </button>
      </div>

      {/* per-model call metrics */}
      <div>
        <p className="text-[10px] uppercase tracking-widest text-light-muted mb-1.5">Calls by model</p>
        {models.length === 0 ? (
          <div className="text-xs text-light-muted">No model calls recorded yet — run a task.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead className="text-light-muted text-left">
                <tr className="border-b border-light-border dark:border-dark-border">
                  <th className="py-1 pr-2 font-medium">model</th>
                  <th className="py-1 px-2 font-medium text-right">calls</th>
                  <th className="py-1 px-2 font-medium text-right">errors</th>
                  <th className="py-1 px-2 font-medium text-right">avg s</th>
                  <th className="py-1 px-2 font-medium text-right">fallbk</th>
                  <th className="py-1 pl-2 font-medium text-right">cost $</th>
                </tr>
              </thead>
              <tbody className="font-code">
                {models.map((m) => (
                  <tr key={m.model} className="border-b border-light-border/40 dark:border-dark-border/40">
                    <td className="py-1 pr-2 truncate max-w-[150px]" title={m.model}>{shortModel(m.model)}</td>
                    <td className="py-1 px-2 text-right">{m.calls}</td>
                    <td className={`py-1 px-2 text-right ${m.errors ? "text-red-500" : ""}`}>{m.errors}</td>
                    <td className="py-1 px-2 text-right">{m.avg_latency ?? "–"}</td>
                    <td className={`py-1 px-2 text-right ${m.fallbacks ? "text-amber-500" : ""}`}>{m.fallbacks}</td>
                    <td className="py-1 pl-2 text-right">{(m.cost || 0).toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* per-key pool usage */}
      <div>
        <p className="text-[10px] uppercase tracking-widest text-light-muted mb-1.5">API key pool (per-minute usage)</p>
        {keyProviders.length === 0 ? (
          <div className="text-xs text-light-muted">No pooled keys (add some in Fleet &amp; keys).</div>
        ) : keyProviders.map(([prov, keys]) => (
          <div key={prov} className="mb-2">
            <div className="text-[11px] font-medium">{prov}</div>
            {(keys as any[]).map((k, i) => (
              <Bar key={i} label={k.key}>
                {k.used}/{k.rpm} rpm{k.cooldown_s > 0 ? ` · cooldown ${k.cooldown_s}s` : ""}{!k.enabled ? " · disabled" : ""}
              </Bar>
            ))}
          </div>
        ))}
      </div>

      {/* cache hit-rates */}
      <div>
        <p className="text-[10px] uppercase tracking-widest text-light-muted mb-1.5">Cache hit-rates</p>
        {caches.length === 0 ? (
          <div className="text-xs text-light-muted">No cache activity yet.</div>
        ) : caches.map(([name, s]: any) => (
          <Bar key={name} label={name}>
            {Math.round((s.hit_rate || 0) * 100)}% · {s.hits}/{s.hits + s.misses} hits · {s.entries} entries
          </Bar>
        ))}
      </div>

      <p className="text-[10px] text-light-muted">Refreshes every 5s while open. Metrics are in-memory (per server run).</p>
    </div>
  );
}
