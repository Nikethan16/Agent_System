import { useEffect, useState } from "react";
import { useStore } from "../lib/store";

// Settings → Memory. Two kinds:
//  - FACTS (semantic): durable facts about you, learned automatically.
//  - RULES (procedural): operating rules. Proposed ones await approval; only
//    approved rules are ever followed.
export default function MemoryPanel() {
  const { facts, loadFacts, forgetFact, addFact,
          rules, loadRules, approveRule, deleteRule, addRule } = useStore();
  const [text, setText] = useState("");
  const [key, setKey] = useState("");
  const [ruleText, setRuleText] = useState("");

  useEffect(() => { loadFacts(); loadRules(); }, []);

  const add = () => { if (!text.trim() || !key.trim()) return; addFact(text, key); setText(""); setKey(""); };
  const addR = () => { if (!ruleText.trim()) return; addRule(ruleText); setRuleText(""); };

  const proposed = rules.filter((r) => r.status === "proposed");
  const active = rules.filter((r) => r.status === "active");
  const field = "text-xs bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2.5 py-1.5 outline-none focus:border-accent-terracotta/40 transition";
  const addBtn = "px-2.5 rounded-lg bg-accent-terracotta hover:bg-accent-deep text-white flex items-center disabled:opacity-40 transition";

  return (
    <div className="space-y-6">
      {/* ---- FACTS ---- */}
      <div>
        <p className="text-[10px] uppercase tracking-widest text-light-muted mb-1">Facts</p>
        <p className="text-[11px] text-light-muted mb-3 leading-relaxed">
          Durable things the assistant remembers about you across chats — learned automatically. Review, add, or forget any.
        </p>
        <div className="flex gap-1.5 mb-3">
          <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="key" aria-label="Fact key" className={field + " w-24"} />
          <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") add(); }}
            placeholder="fact (e.g. prefers Python)" aria-label="Fact text" className={field + " flex-1"} />
          <button onClick={add} title="Add fact" aria-label="Add fact" disabled={!text.trim() || !key.trim()} className={addBtn}>
            <span className="material-symbols-outlined text-[16px]">add</span>
          </button>
        </div>
        <div className="space-y-2">
          {facts.length === 0 && <div className="text-light-muted text-xs">Nothing remembered yet.</div>}
          {facts.map((f) => (
            <div key={f.id} className="group border border-light-border dark:border-dark-border rounded-xl p-3 bg-white dark:bg-dark-surface flex items-start gap-2.5">
              <span className="material-symbols-outlined text-accent-terracotta text-[18px] mt-0.5">psychology</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm break-words">{f.text}</p>
                <p className="text-[10px] text-light-muted uppercase tracking-tight mt-0.5">{f.key}{f.scope && f.scope !== "global" ? ` · ${f.scope}` : ""}</p>
              </div>
              <button onClick={() => forgetFact(f.id)} title="Forget" aria-label="Forget this fact"
                className="material-symbols-outlined text-[16px] text-light-muted opacity-0 group-hover:opacity-100 hover:text-red-500 transition">delete</button>
            </div>
          ))}
        </div>
      </div>

      {/* ---- RULES ---- */}
      <div className="border-t border-light-border dark:border-dark-border pt-5">
        <p className="text-[10px] uppercase tracking-widest text-light-muted mb-1">Rules</p>
        <p className="text-[11px] text-light-muted mb-3 leading-relaxed">
          Operating rules the assistant follows. Proposed rules come from past work — <b>only rules you approve are ever followed</b>.
        </p>
        <div className="flex gap-1.5 mb-3">
          <input value={ruleText} onChange={(e) => setRuleText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") addR(); }}
            placeholder="add a rule (active immediately)" aria-label="Rule text" className={field + " flex-1"} />
          <button onClick={addR} title="Add rule" aria-label="Add rule" disabled={!ruleText.trim()} className={addBtn}>
            <span className="material-symbols-outlined text-[16px]">add</span>
          </button>
        </div>

        {proposed.length > 0 && (
          <div className="mb-3">
            <p className="text-[10px] uppercase tracking-widest text-amber-600 dark:text-amber-400 mb-1.5">Proposed · needs review</p>
            <div className="space-y-2">
              {proposed.map((r) => (
                <div key={r.id} className="border border-amber-300/60 dark:border-amber-500/30 bg-amber-50/50 dark:bg-amber-950/20 rounded-xl p-3">
                  <p className="text-sm break-words mb-2">{r.text}</p>
                  <div className="flex gap-2">
                    <button onClick={() => approveRule(r.id)} className="flex-1 py-1.5 text-[11px] uppercase tracking-wide bg-accent-terracotta hover:bg-accent-deep text-white rounded-lg transition">Approve</button>
                    <button onClick={() => deleteRule(r.id)} className="flex-1 py-1.5 text-[11px] uppercase tracking-wide border border-light-border dark:border-dark-border rounded-lg hover:bg-surface-container-low dark:hover:bg-dark-bg transition">Reject</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-2">
          {active.length > 0 && <p className="text-[10px] uppercase tracking-widest text-light-muted mb-1">Active</p>}
          {active.length === 0 && proposed.length === 0 && (
            <div className="text-light-muted text-xs">No rules yet. The agent may propose some after complex tasks.</div>
          )}
          {active.map((r) => (
            <div key={r.id} className="group border border-light-border dark:border-dark-border rounded-xl p-3 bg-white dark:bg-dark-surface flex items-start gap-2.5">
              <span className="material-symbols-outlined text-emerald-600 dark:text-emerald-400 text-[18px] mt-0.5">rule</span>
              <p className="flex-1 min-w-0 text-sm break-words">{r.text}</p>
              <button onClick={() => deleteRule(r.id)} title="Remove rule" aria-label="Remove rule"
                className="material-symbols-outlined text-[16px] text-light-muted opacity-0 group-hover:opacity-100 hover:text-red-500 transition">delete</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
