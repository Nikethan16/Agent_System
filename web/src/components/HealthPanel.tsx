import { useEffect, useState } from "react";
import { api } from "../lib/api";

// Model Health: per-model call metrics (latency / errors / fallbacks / cost), per-key
// pool usage, and cache hit-rates. This is the call-level view the event feed lacked —
// it answers "which models are slow / erroring / getting fallen-back-from?" for tuning
// the multi-key NVIDIA fleet, and shows how much the caches are saving.
type Health = {
  keys: Record<string, any[]>;
  models: any[];
  breakers: any[];
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

function Tile({ label, value, tone }: { label: string; value: any; tone?: "good" | "warn" | "crit" }) {
  const c = tone === "crit" ? "text-red-500" : tone === "warn" ? "text-amber-500" : "text-on-surface dark:text-dark-text";
  return (
    <div className="flex-1 min-w-[68px] rounded-xl border border-light-border dark:border-dark-border bg-surface-container-low/50 dark:bg-dark-bg/40 px-3 py-2">
      <div className={`text-[15px] font-semibold tabular-nums leading-tight ${c}`}>{value}</div>
      <div className="text-[9px] uppercase tracking-[0.08em] text-light-muted mt-0.5">{label}</div>
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
  const breakers = data.breakers || [];
  const caches = Object.entries(data.caches || {});
  const keyProviders = Object.entries(data.keys || {});

  // Fleet-wide summary (surfaced before the per-model detail).
  const totalCalls = models.reduce((n, m) => n + (m.calls || 0), 0);
  const totalErrors = models.reduce((n, m) => n + (m.errors || 0), 0);
  const totalCost = models.reduce((n, m) => n + (m.cost || 0), 0);
  const errRate = totalCalls ? totalErrors / totalCalls : 0;
  const latModels = models.filter((m) => m.avg_latency != null && m.calls);
  const avgLatency = latModels.length
    ? latModels.reduce((n, m) => n + m.avg_latency * m.calls, 0) / latModels.reduce((n, m) => n + m.calls, 0)
    : null;
  const openBreakers = breakers.filter((b) => b.open).length;
  const status = openBreakers || errRate > 0.25
    ? { label: "Issues", cls: "text-red-600 dark:text-red-400 bg-red-500/12", dot: "bg-red-500" }
    : errRate > 0.05 || breakers.some((b) => b.fails)
    ? { label: "Degraded", cls: "text-amber-700 dark:text-amber-400 bg-amber-500/12", dot: "bg-amber-500" }
    : { label: "Healthy", cls: "text-emerald-700 dark:text-emerald-400 bg-emerald-500/12", dot: "bg-emerald-500" };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="text-sm font-medium">Model health</div>
          <span className={`inline-flex items-center gap-1.5 text-[10.5px] font-semibold px-2 py-0.5 rounded-full ${status.cls}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />{status.label}
          </span>
        </div>
        <button onClick={reset} className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg border border-light-border dark:border-dark-border hover:bg-surface-container-low dark:hover:bg-dark-bg">
          <span className="material-symbols-outlined text-[14px]">restart_alt</span>Reset metrics
        </button>
      </div>

      {/* fleet-wide summary tiles */}
      {totalCalls > 0 && (
        <div className="flex gap-2 flex-wrap">
          <Tile label="calls" value={totalCalls.toLocaleString()} />
          <Tile label="errors" value={totalErrors} tone={totalErrors ? (errRate > 0.25 ? "crit" : "warn") : undefined} />
          <Tile label="err rate" value={`${(errRate * 100).toFixed(errRate < 0.1 ? 1 : 0)}%`} tone={errRate > 0.25 ? "crit" : errRate > 0.05 ? "warn" : undefined} />
          <Tile label="avg s" value={avgLatency != null ? avgLatency.toFixed(1) : "–"} />
          <Tile label="cost $" value={totalCost.toFixed(3)} />
        </div>
      )}

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
                  <th className="py-1 px-2 font-medium text-right">reliab</th>
                  <th className="py-1 px-2 font-medium text-right">calls</th>
                  <th className="py-1 px-2 font-medium text-right">errors</th>
                  <th className="py-1 px-2 font-medium text-right">avg s</th>
                  <th className="py-1 px-2 font-medium text-right">fallbk</th>
                  <th className="py-1 px-2 font-medium text-right">cache</th>
                  <th className="py-1 pl-2 font-medium text-right">cost $</th>
                </tr>
              </thead>
              <tbody className="font-code">
                {models.map((m) => (
                  <tr key={m.model} className="border-b border-light-border/40 dark:border-dark-border/40">
                    <td className="py-1 pr-2 truncate max-w-[150px]" title={m.model}>
                      <span className="inline-flex items-center gap-1.5">
                        {shortModel(m.model)}
                        {m.degraded && <span title="High recent error rate — the router is deprioritizing this model"
                          className="shrink-0 text-[8px] uppercase tracking-wide font-bold px-1 py-px rounded bg-red-500/12 text-red-600 dark:text-red-400">degraded</span>}
                      </span>
                    </td>
                    <td className={`py-1 px-2 text-right ${m.degraded ? "text-red-500" : m.reliability != null && m.reliability < 0.9 ? "text-amber-500" : "text-emerald-600 dark:text-emerald-400"}`}>
                      {m.reliability != null ? `${Math.round(m.reliability * 100)}%` : "–"}
                    </td>
                    <td className="py-1 px-2 text-right">{m.calls}</td>
                    <td className={`py-1 px-2 text-right ${m.errors ? "text-red-500" : ""}`}>{m.errors}</td>
                    <td className="py-1 px-2 text-right">{m.avg_latency ?? "–"}</td>
                    <td className={`py-1 px-2 text-right ${m.fallbacks ? "text-amber-500" : ""}`}>{m.fallbacks}</td>
                    <td className="py-1 px-2 text-right">{m.cache_hit_rate != null ? `${Math.round(m.cache_hit_rate * 100)}%` : "–"}</td>
                    <td className="py-1 pl-2 text-right">{(m.cost || 0).toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* circuit breakers — only models the breaker is currently tracking */}
      {breakers.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-light-muted mb-1.5">Circuit breakers</p>
          <div className="space-y-1">
            {breakers.map((b) => (
              <div key={b.model} className="flex items-center justify-between text-[11px] py-0.5">
                <span className="font-code truncate mr-2">{shortModel(b.model)}</span>
                {b.open ? (
                  <span className="shrink-0 inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full text-red-600 dark:text-red-400 bg-red-500/12">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-500" />open · {b.cooldown_s}s
                  </span>
                ) : (
                  <span className="shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded-full text-amber-700 dark:text-amber-400 bg-amber-500/12">
                    {b.fails}/{b.threshold} fails
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* per-key pool usage */}
      <div>
        <p className="text-[10px] uppercase tracking-widest text-light-muted mb-1.5">API key pool (per-minute usage)</p>
        {keyProviders.length === 0 ? (
          <div className="text-xs text-light-muted">No pooled keys (add some in Fleet &amp; keys).</div>
        ) : keyProviders.map(([prov, keys]) => {
          const ks = keys as any[];
          const live = ks.filter((k) => k.enabled);
          const used = ks.reduce((n, k) => n + (k.used || 0), 0);
          const cap = ks.reduce((n, k) => n + (k.rpm || 0), 0);
          const cooling = ks.filter((k) => k.cooldown_s > 0).length;
          return (
            <div key={prov} className="mb-2">
              <div className="flex items-center justify-between text-[11px] font-medium">
                <span>{prov}</span>
                <span className="font-code text-light-muted">
                  {live.length}/{ks.length} keys · {used}/{cap} rpm{cooling ? ` · ${cooling} cooling` : ""}
                </span>
              </div>
              {ks.map((k, i) => (
                <Bar key={i} label={k.key}>
                  {k.used}/{k.rpm} rpm{k.cooldown_s > 0 ? ` · cooldown ${k.cooldown_s}s` : ""}{!k.enabled ? " · disabled" : ""}
                </Bar>
              ))}
            </div>
          );
        })}
      </div>

      {/* cache hit-rates */}
      <div>
        <p className="text-[10px] uppercase tracking-widest text-light-muted mb-1.5">Cache hit-rates</p>
        {caches.length === 0 ? (
          <div className="text-xs text-light-muted">No cache activity yet.</div>
        ) : caches.map(([name, s]: any) => {
          const pct = Math.round((s.hit_rate || 0) * 100);
          return (
            <div key={name} className="py-1">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-light-muted truncate mr-2">{name}</span>
                <span className="font-code text-[10px] text-light-muted">{s.hits}/{s.hits + s.misses} · {s.entries} entries</span>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <div className="flex-1 h-1.5 rounded-full bg-surface-container-high dark:bg-dark-border overflow-hidden">
                  <div className="h-full rounded-full bg-accent-terracotta" style={{ width: `${pct}%` }} />
                </div>
                <span className="font-code text-[11px] font-semibold tabular-nums w-9 text-right">{pct}%</span>
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[10px] text-light-muted">Refreshes every 5s while open. Metrics are in-memory (per server run).</p>
    </div>
  );
}
