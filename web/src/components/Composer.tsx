import { useState } from "react";
import { useStore } from "../lib/store";

const MODES = ["auto", "careful", "trusted"] as const;

function Toggle({ on, set, label, title }: { on: boolean; set: (v: boolean) => void; label: string; title?: string }) {
  return (
    <label title={title} className="flex items-center gap-1.5 cursor-pointer group select-none">
      <input type="checkbox" className="hidden peer" checked={on} onChange={(e) => set(e.target.checked)} />
      <span className="w-3.5 h-3.5 rounded-sm border border-light-muted peer-checked:bg-accent-terracotta peer-checked:border-accent-terracotta flex items-center justify-center transition">
        {on && <span className="material-symbols-outlined text-white text-[10px] leading-none">check</span>}
      </span>
      <span className="text-[10px] uppercase tracking-wide text-light-muted group-hover:text-on-surface dark:group-hover:text-dark-text">{label}</span>
    </label>
  );
}

export default function Composer() {
  const {
    submit, stop, running, maxUsd, maxIter, setLimit, mode, setMode,
    planFirst, setPlanFirst, review, setReview, parallel, setParallel, stream, setStream,
    enqueueJob, attachments, addAttachment, removeAttachment,
  } = useStore();
  const [text, setText] = useState("");

  const go = () => {
    const t = text.trim();
    if (!t || running) return;
    submit(t);
    setText("");
  };

  const num = (e: React.ChangeEvent<HTMLInputElement>, k: "maxUsd" | "maxIter") => {
    const n = parseFloat(e.target.value);
    if (!Number.isNaN(n)) setLimit(k, n);   // allow 0; don't snap back to a default
  };

  const queue = () => {
    const t = text.trim();
    if (!t) return;
    enqueueJob(t);
    setText("");
  };

  return (
    <div className="px-gutter pb-6 pt-2 flex flex-col items-center bg-gradient-to-t from-surface dark:from-dark-bg via-surface dark:via-dark-bg to-transparent">
      <div className="w-full max-w-[760px] bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-sm p-2 focus-within:ring-2 focus-within:ring-accent-terracotta/15 transition">
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-2 pt-1 pb-2">
            {attachments.map((a) => (
              <span key={a.path} className="flex items-center gap-1 text-[11px] bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-full px-2 py-0.5">
                <span className="material-symbols-outlined text-[14px] text-accent-terracotta">attach_file</span>
                {a.name}
                <span onClick={() => removeAttachment(a.path)} className="material-symbols-outlined text-[14px] text-light-muted hover:text-red-500 cursor-pointer">close</span>
              </span>
            ))}
          </div>
        )}
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(); } }}
          placeholder="Describe a task — coding or general. Hard goals split across specialist agents."
          className="w-full px-3 py-2.5 bg-transparent resize-none outline-none text-[15px] min-h-[56px] placeholder-light-muted"
        />
        <div className="flex items-center justify-between px-1 pt-2 border-t border-light-border/50 dark:border-dark-border gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center bg-surface-container-low dark:bg-dark-bg p-1 rounded-lg">
              {MODES.map((m) => (
                <button key={m} onClick={() => setMode(m)}
                  title={m === "auto" ? "Ask only for irreversible actions" : m === "careful" ? "Ask for every risky action" : "Auto-approve all but hard-blocks"}
                  className={`px-2.5 py-1 text-[10px] uppercase tracking-wide rounded transition ${mode === m ? "bg-white dark:bg-dark-surface shadow-sm text-on-surface dark:text-dark-text border border-light-border dark:border-dark-border" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text"}`}>{m}</button>
              ))}
            </div>
            <div className="h-4 w-px bg-light-border dark:bg-dark-border mx-1" />
            <Toggle on={planFirst} set={setPlanFirst} label="Plan first" title="Preview a plan and approve before running" />
            <Toggle on={review} set={setReview} label="Force QA" title="QA already runs automatically on substantive tasks; enable to force it on every task" />
            <Toggle on={parallel} set={setParallel} label="Parallel" title="Run independent subtasks concurrently" />
            <Toggle on={stream} set={setStream} label="Stream" title="Stream tokens live as the agent works (on by default)" />
            <div className="h-4 w-px bg-light-border dark:bg-dark-border mx-1" />
            <label className="text-[10px] uppercase tracking-wide text-light-muted flex items-center gap-1">$
              <input type="number" min="0" step="0.05" value={maxUsd} aria-label="Max cost per run in dollars"
                onChange={(e) => num(e, "maxUsd")}
                className="w-12 bg-surface-container-low dark:bg-dark-bg rounded px-1.5 py-0.5 outline-none" /></label>
            <label className="text-[10px] uppercase tracking-wide text-light-muted flex items-center gap-1">loops
              <input type="number" min="1" value={maxIter} aria-label="Max loops per run"
                onChange={(e) => num(e, "maxIter")}
                className="w-12 bg-surface-container-low dark:bg-dark-bg rounded px-1.5 py-0.5 outline-none" /></label>
          </div>
          <div className="flex items-center gap-1.5">
            <label title="Attach a file (added as context)"
              className="w-9 h-9 rounded-xl text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg flex items-center justify-center transition cursor-pointer">
              <span className="material-symbols-outlined text-[20px]">attach_file</span>
              <input type="file" className="hidden" onChange={(e) => {
                const f = e.target.files?.[0]; if (f) addAttachment(f); e.currentTarget.value = "";
              }} />
            </label>
            <button onClick={queue} disabled={!text.trim() || running} title="Queue as a background task (runs unattended)" aria-label="Queue as background task"
              className="w-9 h-9 rounded-xl text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg flex items-center justify-center transition disabled:opacity-30">
              <span className="material-symbols-outlined text-[20px]">schedule</span>
            </button>
            {running ? (
              <button onClick={() => stop()} aria-label="Stop the running task" className="w-10 h-10 rounded-xl border border-red-300 text-red-500 flex items-center justify-center hover:bg-red-50 dark:hover:bg-red-950/30 transition">
                <span className="material-symbols-outlined">stop</span>
              </button>
            ) : (
              <button onClick={go} disabled={!text.trim()} aria-label="Send message" className="w-10 h-10 bg-accent-terracotta text-white rounded-xl flex items-center justify-center hover:brightness-110 active:scale-95 transition shadow disabled:opacity-40">
                <span className="material-symbols-outlined">arrow_upward</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
