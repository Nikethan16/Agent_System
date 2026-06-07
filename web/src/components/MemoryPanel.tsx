import { useEffect, useState } from "react";
import { useStore } from "../lib/store";

// Shows everything the agent remembers and gives full control:
//  - FACTS (semantic memory): durable facts about you, learned automatically.
//  - RULES (procedural memory): operating rules. Proposed ones await your approval;
//    only approved rules are ever followed.
export default function MemoryPanel() {
  const { facts, loadFacts, forgetFact, addFact,
          rules, loadRules, approveRule, deleteRule, addRule } = useStore();
  const [text, setText] = useState("");
  const [key, setKey] = useState("");
  const [ruleText, setRuleText] = useState("");

  useEffect(() => { loadFacts(); loadRules(); }, []);

  const add = () => {
    if (!text.trim() || !key.trim()) return;
    addFact(text, key);
    setText(""); setKey("");
  };
  const addR = () => {
    if (!ruleText.trim()) return;
    addRule(ruleText);
    setRuleText("");
  };

  const proposed = rules.filter((r) => r.status === "proposed");
  const active = rules.filter((r) => r.status === "active");

  return (
    <div className="flex flex-col h-full overflow-y-auto scrollbar">
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <h4 className="text-[11px] uppercase tracking-widest text-light-muted">Memory</h4>
        <button onClick={() => { loadFacts(); loadRules(); }} title="Refresh" aria-label="Refresh memory"
          className="p-1 rounded-md text-light-muted hover:text-on-surface dark:hover:text-dark-text transition">
          <span className="material-symbols-outlined text-[16px]">refresh</span>
        </button>
      </div>

      {/* ---- FACTS ---- */}
      <p className="px-5 pb-2 text-[11px] leading-4 text-light-muted">
        <b>Facts</b> — durable things the assistant remembers about you across chats. It
        learns these automatically; review, add, or forget any here.
      </p>
      <div className="px-4 pb-3">
        <div className="flex gap-1.5">
          <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="key" aria-label="Fact key"
            className="w-24 text-xs bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1.5 outline-none" />
          <input value={text} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") add(); }} placeholder="fact (e.g. prefers Python)" aria-label="Fact text"
            className="flex-1 text-xs bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1.5 outline-none" />
          <button onClick={add} title="Add fact" aria-label="Add fact" disabled={!text.trim() || !key.trim()}
            className="px-2 rounded-lg bg-accent-terracotta text-white text-xs hover:brightness-110 active:scale-95 transition disabled:opacity-40">
            <span className="material-symbols-outlined text-[16px]">add</span>
          </button>
        </div>
      </div>
      <div className="px-4 space-y-2">
        {facts.length === 0 && <div className="text-light-muted text-xs px-1 py-1">Nothing remembered yet.</div>}
        {facts.map((f) => (
          <div key={f.id} className="group border border-light-border dark:border-dark-border rounded-xl p-3 bg-white dark:bg-dark-surface flex items-start gap-2">
            <span className="material-symbols-outlined text-accent-terracotta text-[18px] mt-0.5">psychology</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm break-words">{f.text}</p>
              <p className="text-[10px] text-light-muted uppercase tracking-tight mt-0.5">
                {f.key}{f.scope && f.scope !== "global" ? ` · ${f.scope}` : ""}
              </p>
            </div>
            <button onClick={() => forgetFact(f.id)} title="Forget" aria-label="Forget this fact"
              className="material-symbols-outlined text-[16px] text-light-muted opacity-0 group-hover:opacity-100 hover:text-red-500 transition">delete</button>
          </div>
        ))}
      </div>

      {/* ---- RULES ---- */}
      <div className="mt-5 border-t border-light-border dark:border-dark-border pt-3">
        <p className="px-5 pb-2 text-[11px] leading-4 text-light-muted">
          <b>Rules</b> — operating rules the assistant follows. Proposed rules are
          suggestions from past work; <b>only rules you approve are ever followed</b>.
        </p>
        <div className="px-4 pb-3">
          <div className="flex gap-1.5">
            <input value={ruleText} onChange={(e) => setRuleText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") addR(); }} placeholder="add a rule (active immediately)" aria-label="Rule text"
              className="flex-1 text-xs bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1.5 outline-none" />
            <button onClick={addR} title="Add rule" aria-label="Add rule" disabled={!ruleText.trim()}
              className="px-2 rounded-lg bg-accent-terracotta text-white text-xs hover:brightness-110 active:scale-95 transition disabled:opacity-40">
              <span className="material-symbols-outlined text-[16px]">add</span>
            </button>
          </div>
        </div>

        {proposed.length > 0 && (
          <div className="px-4 pb-2">
            <p className="text-[10px] uppercase tracking-widest text-amber-600 dark:text-amber-400 mb-1.5 px-1">Proposed · needs review</p>
            <div className="space-y-2">
              {proposed.map((r) => (
                <div key={r.id} className="border border-amber-300/60 dark:border-amber-500/30 bg-amber-50/50 dark:bg-amber-950/20 rounded-xl p-3">
                  <p className="text-sm break-words mb-2">{r.text}</p>
                  <div className="flex gap-2">
                    <button onClick={() => approveRule(r.id)}
                      className="flex-1 py-1 text-[11px] uppercase tracking-wide bg-accent-terracotta text-white rounded-lg hover:brightness-110 active:scale-95 transition">Approve</button>
                    <button onClick={() => deleteRule(r.id)}
                      className="flex-1 py-1 text-[11px] uppercase tracking-wide border border-light-border dark:border-dark-border rounded-lg hover:bg-surface-container-low dark:hover:bg-dark-bg transition">Reject</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="px-4 pb-5 space-y-2">
          {active.length > 0 && <p className="text-[10px] uppercase tracking-widest text-light-muted mb-1 px-1">Active</p>}
          {active.length === 0 && proposed.length === 0 && (
            <div className="text-light-muted text-xs px-1 py-1">No rules yet. The agent may propose some after complex tasks.</div>
          )}
          {active.map((r) => (
            <div key={r.id} className="group border border-light-border dark:border-dark-border rounded-xl p-3 bg-white dark:bg-dark-surface flex items-start gap-2">
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
