import { useState, useRef, useEffect } from "react";
import { useStore } from "../lib/store";

const MODES = ["auto", "careful", "trusted"] as const;

function Toggle({ on, set, label, hint }: { on: boolean; set: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <button type="button" onClick={() => set(!on)} className="w-full flex items-center justify-between gap-3 py-1.5 text-left select-none">
      <span className="min-w-0">
        <span className="block text-[13px] text-on-surface dark:text-dark-text">{label}</span>
        {hint && <span className="block text-[10.5px] text-light-muted leading-tight">{hint}</span>}
      </span>
      <span className={`relative w-9 h-5 rounded-full transition shrink-0 ${on ? "bg-accent-terracotta" : "bg-surface-container-highest dark:bg-dark-border"}`}>
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform ${on ? "translate-x-4" : ""}`} />
      </span>
    </button>
  );
}

function Section({ label, children }: { label: string; children: any }) {
  return (
    <div className="py-3 border-t border-light-border/60 dark:border-dark-border first:border-t-0 first:pt-1">
      <p className="text-[10px] uppercase tracking-widest text-light-muted mb-2">{label}</p>
      {children}
    </div>
  );
}

// All per-run controls live here (approval mode, behavior toggles, limits) so the
// composer bar itself stays minimal. Defaults live in Settings; edits here are this-run-only.
function RunOptions({ onClose, onQueue, canQueue }: { onClose: () => void; onQueue: () => void; canQueue: boolean }) {
  const { maxUsd, maxIter, setLimit, mode, setMode, planFirst, setPlanFirst, review, setReview, parallel, setParallel, stream, setStream, acceptance, setAcceptance } = useStore();
  const num = (e: React.ChangeEvent<HTMLInputElement>, k: "maxUsd" | "maxIter") => {
    const n = parseFloat(e.target.value); if (!Number.isNaN(n)) setLimit(k, n);
  };
  const help = mode === "auto" ? "Asks only for irreversible actions." : mode === "careful" ? "Asks before every risky action." : "Auto-approves all but hard-blocks.";
  const field = "w-full mt-1 bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2.5 py-1.5 text-sm text-on-surface dark:text-dark-text outline-none focus:border-accent-terracotta/40 transition";
  return (
    <div className="absolute bottom-14 left-0 w-80 bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-xl p-4 z-20 fadeup">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium">Run options</span>
        <button onClick={onClose} aria-label="Close run options" className="material-symbols-outlined text-[18px] text-light-muted hover:text-on-surface dark:hover:text-dark-text">close</button>
      </div>

      <Section label="Approval for this run">
        <div className="flex items-center bg-surface-container-low dark:bg-dark-bg p-1 rounded-xl">
          {MODES.map((m) => (
            <button key={m} onClick={() => setMode(m)}
              className={`flex-1 px-2 py-1.5 text-[11px] capitalize rounded-lg transition ${mode === m ? "bg-white dark:bg-dark-surface shadow-sm font-medium" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text"}`}>{m}</button>
          ))}
        </div>
        <p className="text-[11px] text-light-muted mt-2">{help}</p>
      </Section>

      <Section label="Behavior">
        <Toggle on={planFirst} set={setPlanFirst} label="Plan first" hint="Preview a plan and approve before running" />
        <Toggle on={review} set={setReview} label="Force QA" hint="QA already runs on substantive tasks" />
        <Toggle on={parallel} set={setParallel} label="Parallel subtasks" hint="Run independent subtasks at once" />
        <Toggle on={stream} set={setStream} label="Stream tokens" hint="Show output as it's written" />
      </Section>

      <Section label="Limits for this run">
        <div className="flex items-center gap-3">
          <label className="flex-1 text-[10px] uppercase tracking-wide text-light-muted">Max $
            <input type="number" min="0" step="0.05" value={maxUsd} aria-label="Max cost per run in dollars" onChange={(e) => num(e, "maxUsd")} className={field} /></label>
          <label className="flex-1 text-[10px] uppercase tracking-wide text-light-muted">Max loops
            <input type="number" min="1" value={maxIter} aria-label="Max loops per run" onChange={(e) => num(e, "maxIter")} className={field} /></label>
        </div>
      </Section>

      <Section label="Acceptance criteria (optional)">
        <textarea value={acceptance} onChange={(e) => setAcceptance(e.target.value)}
          placeholder="Definition of done the QA step checks (e.g. 'prints 42; pytest passes')."
          className={field + " resize-none h-14 text-[12px] placeholder-light-muted"} />
      </Section>

      <div className="flex items-center justify-between pt-3 border-t border-light-border/60 dark:border-dark-border">
        <button onClick={() => { if (canQueue) { onQueue(); onClose(); } }} disabled={!canQueue} title="Queue as a background task (runs unattended)"
          className="text-[11px] text-light-muted hover:text-on-surface dark:hover:text-dark-text flex items-center gap-1.5 disabled:opacity-40">
          <span className="material-symbols-outlined text-[15px]">schedule</span> Queue as task
        </button>
        <span className="text-[10px] text-light-muted">this run only</span>
      </div>
    </div>
  );
}

// The composer renders in two places, Claude-style: centered under the greeting on the
// welcome screen (`variant="center"`), and pinned to the bottom during a conversation
// (`variant="bottom"`). The input card itself is identical in both.
export default function Composer({ variant = "bottom" }: { variant?: "center" | "bottom" }) {
  const { submit, stop, running, enqueueJob, attachments, addAttachment, removeAttachment } = useStore();
  const [text, setText] = useState("");
  const [opts, setOpts] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow the textarea up to a cap (Claude-style), then scroll.
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 220) + "px";
  }, [text]);

  // Close the popover on an outside click.
  useEffect(() => {
    if (!opts) return;
    const onDown = (e: MouseEvent) => { if (popRef.current && !popRef.current.contains(e.target as Node)) setOpts(false); };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [opts]);

  const go = () => { const t = text.trim(); if (!t || running) return; submit(t); setText(""); };
  const queue = () => { const t = text.trim(); if (!t) return; enqueueJob(t); setText(""); };

  const placeholder = variant === "center"
    ? "How can I help you today?"
    : "Reply to the team…";

  const box = (
    <div className="w-full bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-[26px] shadow-sm p-2.5 focus-within:border-accent-terracotta/40 focus-within:shadow-md transition-all">
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
        ref={taRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(); } }}
        placeholder={placeholder}
        rows={1}
        className="w-full px-3 pt-2 pb-1 bg-transparent resize-none outline-none text-[15px] leading-6 min-h-[40px] placeholder-light-muted"
      />
      <div className="flex items-center justify-between px-1 pt-1.5 gap-2">
        {/* LEFT: attach + run-options (everything advanced lives behind the sliders) */}
        <div className="flex items-center gap-1">
          <label title="Attach a file (added as context)"
            className="w-9 h-9 rounded-full text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg flex items-center justify-center transition cursor-pointer">
            <span className="material-symbols-outlined text-[22px]">add</span>
            <input type="file" className="hidden" onChange={(e) => {
              const f = e.target.files?.[0]; if (f) addAttachment(f); e.currentTarget.value = "";
            }} />
          </label>
          <div className="relative" ref={popRef}>
            <button onClick={() => setOpts(!opts)} title="Run options — approval, plan-first, QA, parallel, limits" aria-label="Run options"
              className={`flex items-center gap-1.5 h-9 px-3 rounded-full text-[12px] transition ${opts ? "bg-accent-terracotta/10 text-accent-terracotta" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg"}`}>
              <span className="material-symbols-outlined text-[18px]">tune</span>
              <span className="hidden sm:inline">Options</span>
            </button>
            {opts && <RunOptions onClose={() => setOpts(false)} onQueue={queue} canQueue={!!text.trim() && !running} />}
          </div>
        </div>
        {/* RIGHT: send / stop */}
        {running ? (
          <button onClick={() => stop()} aria-label="Stop the running task" className="w-9 h-9 rounded-full border border-red-300 text-red-500 flex items-center justify-center hover:bg-red-50 dark:hover:bg-red-950/30 transition">
            <span className="material-symbols-outlined text-[20px]">stop</span>
          </button>
        ) : (
          <button onClick={go} disabled={!text.trim()} aria-label="Send message"
            className="w-9 h-9 bg-accent-terracotta hover:bg-accent-deep text-white rounded-full flex items-center justify-center active:scale-95 transition shadow-sm disabled:opacity-30 disabled:hover:bg-accent-terracotta">
            <span className="material-symbols-outlined text-[20px]">arrow_upward</span>
          </button>
        )}
      </div>
    </div>
  );

  if (variant === "center") {
    return <div className="w-full max-w-[720px] mx-auto">{box}</div>;
  }

  return (
    <div className="px-gutter pb-4 pt-2 flex flex-col items-center bg-gradient-to-t from-surface dark:from-dark-bg via-surface dark:via-dark-bg to-transparent">
      <div className="w-full max-w-[760px]">{box}</div>
      <p className="text-[10px] text-light-muted mt-2">The team can make mistakes — review important results.</p>
    </div>
  );
}
