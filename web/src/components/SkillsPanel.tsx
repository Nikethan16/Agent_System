import { useEffect, useMemo } from "react";
import { useStore } from "../lib/store";

export default function SkillsPanel() {
  const { skills, loadSkills, messages } = useStore();

  useEffect(() => { if (!skills.length) loadSkills(); }, []);

  // Which skills were applied in this conversation (from `skill` events).
  const applied = useMemo(() => {
    const seen = new Set<string>();
    for (const m of messages)
      for (const ev of m.events || [])
        if (ev.type === "skill") for (const s of ev.skills || []) seen.add(s);
    return seen;
  }, [messages]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <h4 className="text-[11px] uppercase tracking-widest text-light-muted">Skills</h4>
        <button onClick={() => loadSkills()} title="Refresh"
          className="p-1 rounded-md text-light-muted hover:text-on-surface dark:hover:text-dark-text transition">
          <span className="material-symbols-outlined text-[16px]">refresh</span>
        </button>
      </div>
      <p className="px-5 pb-3 text-[11px] leading-4 text-light-muted">
        Expert playbooks the team loads automatically when a task matches — lifting output
        quality. Add more by dropping a folder into <span className="font-code">skills/</span>.
      </p>
      <div className="px-4 space-y-2 overflow-y-auto scrollbar flex-1 min-h-0">
        {skills.length === 0 && <div className="text-light-muted text-xs px-1 py-2">No skills loaded.</div>}
        {skills.map((s) => {
          const on = applied.has(s.name);
          return (
            <div key={s.name}
              className={`border rounded-xl p-3 bg-white dark:bg-dark-surface transition ${on ? "border-accent-terracotta/60" : "border-light-border dark:border-dark-border"}`}>
              <div className="flex items-center gap-2 mb-1">
                <span className="material-symbols-outlined text-accent-terracotta text-[18px]">bolt</span>
                <h3 className="text-sm font-semibold flex-1 truncate font-code">{s.name}</h3>
                {on && (
                  <span className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-accent-terracotta/15 text-accent-terracotta font-bold">
                    applied
                  </span>
                )}
              </div>
              <p className="text-[11px] leading-4 text-on-surface-variant dark:text-light-muted line-clamp-4">
                {s.description}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
