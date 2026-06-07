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
    <div className="p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-[11px] uppercase tracking-widest text-light-muted">Model routing</h4>
        <button onClick={() => scoutModels()}
          className="flex items-center gap-1 text-[11px] text-accent-terracotta hover:brightness-110">
          <span className="material-symbols-outlined text-[16px]">travel_explore</span> scout
        </button>
      </div>
      {cheapest && (
        <p className="text-[11px] text-emerald-600 dark:text-emerald-400 leading-snug">
          Cost-first: auto-picks the cheapest available model per tier.
        </p>
      )}
      {TIERS.filter((t) => tiers[t.k]).map((t) => (
        <div key={t.k} className="border border-light-border dark:border-dark-border rounded-xl p-3 bg-white dark:bg-dark-surface">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] uppercase tracking-widest font-bold text-on-surface dark:text-dark-text">{t.k}</span>
            <span className="text-[10px] text-light-muted uppercase">{t.label}</span>
          </div>
          {cheapest && resolved[t.k] && (
            <div className="text-[11px] text-emerald-600 dark:text-emerald-400 mb-1.5 truncate">using: {resolved[t.k]}</div>
          )}
          <select value={tiers[t.k].model} onChange={(e) => setTier(t.k, e.target.value)}
            className="w-full text-[12px] bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1.5 outline-none">
            {catalog.map((c) => <option key={c.id} value={c.id}>{c.id}</option>)}
          </select>
        </div>
      ))}
    </div>
  );
}
