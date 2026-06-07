import { useState, useRef, useEffect } from "react";
import { useStore } from "../lib/store";

const MODES = ["auto", "careful", "trusted"] as const;

function Toggle({ on, set, label, title }: { on: boolean; set: (v: boolean) => void; label: string; title?: string }) {
  return (
    <label title={title} className="flex items-center justify-between gap-3 cursor-pointer group select-none py-1">
      <span className="text-xs text-on-surface-variant dark:text-light-muted group-hover:text-on-surface dark:group-hover:text-dark-text">{label}</span>
      <input type="checkbox" className="hidden peer" checked={on} onChange={(e) => set(e.target.checked)} />
      <span className="w-4 h-4 rounded border border-light-muted peer-checked:bg-accent-terracotta peer-checked:border-accent-terracotta flex items-center justify-center transition shrink-0">
        {on && <span className="material-symbols-outlined text-white text-[12px] leading-none">check</span>}
      </span>
    </label>
  );
}

// All per-run controls live here (approval mode, behavior toggles, limits) so the
// composer bar itself stays minimal. Defaults live in Settings; edits here are this-run-only.
function RunOptions({ onClose, onQueue, canQueue }: { onClose: () => void; onQueue: () => void; canQueue: boolean }) {
  const { maxUsd, maxIter, setLimit, mode, setMode, planFirst, setPlanFirst, review, setReview, parallel, setParallel, stream, setStream } = useStore();
  const num = (e: React.ChangeEvent<HTMLInputElement>, k: "maxUsd" | "maxIter") => {
    const n = parseFloat(e.target.value); if (!Number.isNaN(n)) setLimit(k, n);
  };
  const help = mode === "auto" ? "Asks only for irreversible actions." : mode === "careful" ? "Asks before every risky action." : "Auto-approves all but hard-blocks.";
  const fieldCls = "w-full mt-0.5 bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded px-2 py-1 text-sm text-on-surface dark:text-dark-text outline-none";
  return (
    <div className="absolute bottom-12 left-0 w-72 bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-xl shadow-xl p-3 z-20 fadeup">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] uppercase tracking-widest font-bold">Run options</span>
        <button onClick={onClose} aria-label="Close run options" className="material-symbols-outlined text-[16px] text-light-muted hover:text-on-surface dark:hover:text-dark-text">close</button>
      </div>

      <p className="text-[9px] uppercase tracking-widest text-light-muted mb-1.5">Approval for this run</p>
      <div className="flex items-center bg-surface-container-low dark:bg-dark-bg p-1 rounded-lg mb-1">
        {MODES.map((m) => (
          <button key={m} onClick={() => setMode(m)}
            className={`flex-1 px-2 py-1 text-[10px] uppercase tracking-wide rounded transition ${mode === m ? "bg-white dark:bg-dark-surface shadow-sm border border-light-border dark:border-dark-border" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text"}`}>{m}</button>
        ))}
      </div>
      <p className="text-[10px] text-light-muted mb-3">{help}</p>

      <p className="text-[9px] uppercase tracking-widest text-light-muted mb-1">Behavior</p>
      <div className="mb-3 border-b border-light-border/50 dark:border-dark-border pb-2">
        <Toggle on={planFirst} set={setPlanFirst} label="Plan first" title="Preview a plan and approve before running" />
        <Toggle on={review} set={setReview} label="Force QA" title="QA already runs on substantive tasks; force it on every task" />
        <Toggle on={parallel} set={setParallel} label="Parallel subtasks" title="Run independent subtasks concurrently" />
        <Toggle on={stream} set={setStream} label="Stream tokens" title="Stream tokens live as the agent works (on by default)" />
      </div>

      <p className="text-[9px] uppercase tracking-widest text-light-muted mb-1.5">Limits for this run</p>
      <div className="flex items-center gap-3 mb-2">
        <label className="flex-1 text-[10px] uppercase tracking-wide text-light-muted">Max $
          <input type="number" min="0" step="0.05" value={maxUsd} aria-label="Max cost per run in dollars" onChange={(e) => num(e, "maxUsd")} className={fieldCls} /></label>
        <label className="flex-1 text-[10px] uppercase tracking-wide text-light-muted">Max loops
          <input type="number" min="1" value={maxIter} aria-label="Max loops per run" onChange={(e) => num(e, "maxIter")} className={fieldCls} /></label>
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-light-border/50 dark:border-dark-border">
        <button onClick={() => { if (canQueue) { onQueue(); onClose(); } }} disabled={!canQueue} title="Queue as a background task (runs unattended)"
          className="text-[10px] uppercase tracking-wide text-light-muted hover:text-on-surface dark:hover:text-dark-text flex items-center gap-1 disabled:opacity-40">
          <span className="material-symbols-outlined text-[14px]">schedule</span> Queue as task
        </button>
        <span className="text-[10px] text-light-muted">this run only</span>
      </div>
    </div>
  );
}

export default function Composer() {
  const { submit, stop, running, enqueueJob, attachments, addAttachment, removeAttachment } = useStore();
  const [text, setText] = useState("");
  const [opts, setOpts] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);

  // Close the popover on an outside click.
  useEffect(() => {
    if (!opts) return;
    const onDown = (e: MouseEvent) => { if (popRef.current && !popRef.current.contains(e.target as Node)) setOpts(false); };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [opts]);

  const go = () => { const t = text.trim(); if (!t || running) return; submit(t); setText(""); };
  const queue = () => { const t = text.trim(); if (!t) return; enqueueJob(t); setText(""); };

  return (
    <div className="px-gutter pb-5 pt-2 flex flex-col items-center bg-gradient-to-t from-surface dark:from-dark-bg via-surface dark:via-dark-bg to-transparent">
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
        <div className="flex items-center justify-between px-1 pt-2 border-t border-light-border/50 dark:border-dark-border gap-2">
          {/* LEFT: the single Run-options control (everything advanced lives behind it) */}
          <div className="relative" ref={popRef}>
            <button onClick={() => setOpts(!opts)} title="Run options — approval, plan-first, QA, parallel, limits" aria-label="Run options"
              className={`flex items-center gap-1.5 h-9 px-2.5 rounded-xl transition ${opts ? "bg-accent-terracotta/10 text-accent-terracotta" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg"}`}>
              <span className="material-symbols-outlined text-[20px]">tune</span>
              <span className="text-[10px] uppercase tracking-wide hidden sm:inline">Run options</span>
            </button>
            {opts && <RunOptions onClose={() => setOpts(false)} onQueue={queue} canQueue={!!text.trim() && !running} />}
          </div>
          {/* RIGHT: attach + send/stop */}
          <div className="flex items-center gap-1.5">
            <label title="Attach a file (added as context)"
              className="w-9 h-9 rounded-xl text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg flex items-center justify-center transition cursor-pointer">
              <span className="material-symbols-outlined text-[20px]">attach_file</span>
              <input type="file" className="hidden" onChange={(e) => {
                const f = e.target.files?.[0]; if (f) addAttachment(f); e.currentTarget.value = "";
              }} />
            </label>
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
      <p className="text-[10px] text-light-muted mt-2">Press Enter to send · Shift+Enter for a new line</p>
    </div>
  );
}
