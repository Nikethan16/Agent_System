import { useStore } from "../lib/store";

const TIERS = [
  { k: "tier1", label: "Fast" },
  { k: "tier2", label: "Balanced" },
  { k: "tier3", label: "Frontier" },
];

export default function ModelRail() {
  const { tiers, catalog, setTier, strategy, resolved, scoutModels } = useStore();
  const cheapest = strategy === "cheapest";
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end">
        <button onClick={() => scoutModels()}
          className="flex items-center gap-1 text-[11px] text-accent-terracotta hover:brightness-110">
          <span className="material-symbols-outlined text-[16px]">travel_explore</span> Discover models
        </button>
      </div>
      {TIERS.filter((t) => tiers[t.k]).map((t) => (
        <div key={t.k} className="border border-light-border dark:border-dark-border rounded-xl p-3.5 bg-white dark:bg-dark-surface">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[13px] font-medium text-on-surface dark:text-dark-text">{t.label}</span>
            <span className="text-[10px] text-light-muted uppercase tracking-widest">{t.k}</span>
          </div>
          {cheapest && resolved[t.k] && (
            <div className="text-[11px] text-emerald-600 dark:text-emerald-400 mb-2 truncate">Using {resolved[t.k]}</div>
          )}
          <select value={tiers[t.k].model} onChange={(e) => setTier(t.k, e.target.value)}
            className="w-full text-[12px] bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2.5 py-2 outline-none focus:border-accent-terracotta/40 transition">
            {catalog.map((c) => <option key={c.id} value={c.id}>{c.id}</option>)}
          </select>
        </div>
      ))}
    </div>
  );
}
