import { useStore } from "../lib/store";

export default function CheckpointsPanel() {
  const { checkpoints, restore } = useStore();
  return (
    <div className="p-5">
      <h4 className="text-[11px] uppercase tracking-widest text-light-muted mb-3">Checkpoints (rewind)</h4>
      {checkpoints.length === 0 && <div className="text-light-muted text-xs">No checkpoints yet — they're taken before each turn.</div>}
      <div className="space-y-2">
        {checkpoints.map((cp) => (
          <div key={cp.id}
            onClick={() => { if (confirm("Restore the workspace to this checkpoint? Current files will be replaced.")) restore(cp.id); }}
            className="group flex items-center gap-2 border border-light-border dark:border-dark-border rounded-xl p-3 bg-white dark:bg-dark-surface cursor-pointer hover:border-accent-terracotta/40 transition">
            <span className="material-symbols-outlined text-[18px] text-light-muted">history</span>
            <span className="flex-1 text-sm truncate">{cp.label || "(snapshot)"}</span>
            <span className="text-[10px] uppercase tracking-wide text-accent-terracotta opacity-0 group-hover:opacity-100 flex items-center gap-0.5">
              <span className="material-symbols-outlined text-[14px]">undo</span> restore
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
