import { useState, useRef, useEffect } from "react";
import { useStore } from "../lib/store";
import { api } from "../lib/api";

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
  const { maxUsd, maxIter, setLimit, mode, setMode, review, setReview, parallel, setParallel, stream, setStream, acceptance, setAcceptance } = useStore();
  const num = (e: React.ChangeEvent<HTMLInputElement>, k: "maxUsd" | "maxIter") => {
    const n = parseFloat(e.target.value); if (!Number.isNaN(n)) setLimit(k, n);
  };
  const help = mode === "auto" ? "Asks only for irreversible actions." : mode === "careful" ? "Asks before every risky action." : "Auto-approves all but hard-blocks.";
  const field = "w-full mt-1 bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2.5 py-1.5 text-sm text-on-surface dark:text-dark-text outline-none focus:border-accent-terracotta/40 transition";
  return (
    <div className="absolute bottom-14 left-0 w-80 max-w-[calc(100vw-2.5rem)] bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-xl p-4 z-20 fadeup">
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
// A compact inline pill dropdown for the composer bar (OpenCode-style Mode/Model/Effort).
// Shows the current value; opens a small menu above the bar. Closes on outside click.
function BarSelect({ label, value, options, onPick, icon }: {
  label: string; value: string; icon?: string;
  options: { value: string; label: string; hint?: string }[];
  onPick: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);
  const cur = options.find((o) => o.value === value);
  return (
    <div className="relative shrink-0" ref={ref}>
      <button type="button" onClick={() => setOpen(!open)} title={label}
        className={`flex items-center gap-1 h-9 px-2.5 rounded-full text-[12px] transition max-w-[10rem] ${open ? "bg-accent-terracotta/10 text-accent-terracotta" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg"}`}>
        {icon && <span className="material-symbols-outlined text-[16px]">{icon}</span>}
        <span className="truncate">{cur?.label ?? value}</span>
        <span className="material-symbols-outlined text-[16px] -ml-0.5 opacity-70">expand_more</span>
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-1 w-60 max-w-[calc(100vw-2rem)] max-h-64 overflow-y-auto scrollbar bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-xl shadow-xl z-30 p-1 fadeup">
          <p className="text-[9px] uppercase tracking-widest text-light-muted px-2 py-1">{label}</p>
          {options.map((o) => (
            <button key={o.value} type="button" onMouseDown={(e) => { e.preventDefault(); onPick(o.value); setOpen(false); }}
              className={`w-full flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg text-left transition ${o.value === value ? "bg-surface-container-low dark:bg-dark-bg" : "hover:bg-surface-container-low dark:hover:bg-dark-bg"}`}>
              <span className="min-w-0">
                <span className="block text-[12px] text-on-surface dark:text-dark-text truncate">{o.label}</span>
                {o.hint && <span className="block text-[10px] text-light-muted truncate">{o.hint}</span>}
              </span>
              {o.value === value && <span className="material-symbols-outlined text-[16px] text-accent-terracotta shrink-0">check</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// A long catalog id like "nvidia_nim/nvidia/nemotron-3-super-120b" -> "nemotron-3-super-120b".
const shortModel = (id: string) => id.split("/").pop() || id;

export default function Composer({ variant = "bottom" }: { variant?: "center" | "bottom" }) {
  const { submit, stop, running, enqueueJob, attachments, addAttachment, removeAttachment,
          files, loadFiles, commands, draft, setDraft,
          planFirst, setPlanFirst, effort, setEffort, modelOverride, setModelOverride, catalog } = useStore();
  const [text, setText] = useState("");
  const [opts, setOpts] = useState(false);
  const [mention, setMention] = useState<{ query: string; start: number } | null>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Voice input: a mic button records audio and transcribes it (Whisper via a provider) into
  // the message box. Shown only when speech-to-text is configured on the server.
  const [micState, setMicState] = useState<"off" | "recording" | "transcribing">("off");
  const [micAvailable, setMicAvailable] = useState(false);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    api.transcribeAvailable().then((r: any) => setMicAvailable(!!r?.available)).catch(() => setMicAvailable(false));
  }, []);

  const toggleMic = async () => {
    if (micState === "recording") { recRef.current?.stop(); return; }
    if (micState === "transcribing") return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data); };
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setMicState("transcribing");
        try {
          const blob = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
          const r = await api.transcribe(blob);
          const said = (r?.text || "").trim();
          if (said) setText((prev) => (prev ? prev.replace(/\s*$/, " ") : "") + said);
          requestAnimationFrame(() => taRef.current?.focus());
        } catch (err) { console.error("transcription failed", err); }
        finally { setMicState("off"); }
      };
      rec.start();
      recRef.current = rec;
      setMicState("recording");
    } catch (err) { console.error("mic access denied", err); setMicState("off"); }
  };

  // /command menu: opens while the whole input is a bare "/name" (no space/args yet).
  const slashQuery = /^\/([\w-]*)$/.exec(text.trim());
  const cmdMatches = slashQuery
    ? (commands || []).filter((c) => c.name.startsWith(slashQuery[1].toLowerCase())).slice(0, 7)
    : [];

  const pickCommand = (name: string) => {
    setText("/" + name + " ");
    requestAnimationFrame(() => taRef.current?.focus());
  };

  // A palette selection (⌘K) drops a draft here — load it into the composer and focus.
  useEffect(() => {
    if (!draft) return;
    setText(draft);
    setDraft("");
    requestAnimationFrame(() => { const ta = taRef.current; if (ta) { ta.focus(); const n = ta.value.length; ta.setSelectionRange(n, n); } });
  }, [draft]);

  // @file mention: workspace file paths that match the current @token (top 7).
  const filePaths: string[] = (files || []).map((f: any) => typeof f === "string" ? f : f?.path).filter(Boolean);
  const matches = mention
    ? filePaths.filter((p) => p.toLowerCase().includes(mention.query.toLowerCase())).slice(0, 7)
    : [];

  // On every keystroke, detect an @token immediately before the caret -> open the picker.
  const onType = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value; setText(val);
    const caret = e.target.selectionStart ?? val.length;
    const m = val.slice(0, caret).match(/(?:^|\s)@([\w./\-]*)$/);
    if (m) { setMention({ query: m[1], start: caret - m[1].length - 1 }); if (!filePaths.length) loadFiles(); }
    else if (mention) setMention(null);
  };

  const pickFile = (path: string) => {
    const ta = taRef.current; if (!ta || !mention) return;
    const caret = ta.selectionStart ?? text.length;
    const next = text.slice(0, mention.start) + "@" + path + " " + text.slice(caret);
    setText(next); setMention(null);
    requestAnimationFrame(() => { ta.focus(); const pos = mention.start + path.length + 2; ta.setSelectionRange(pos, pos); });
  };

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

  // Inline composer controls (OpenCode-style). Mode maps to plan-first; Model "" = Auto
  // routing; Effort scales how hard the run tries (budget/iterations + QA default).
  const modeOpts = [
    { value: "build", label: "Build", hint: "Do the work now" },
    { value: "plan", label: "Plan first", hint: "Preview a plan, then approve" }];
  const modelOpts = [
    { value: "", label: "Auto", hint: "Cost-first routing (recommended)" },
    // Only models whose provider key is set (available !== false keeps older cached lists working).
    ...(catalog || []).filter((m: any) => m.available !== false).map((m: any) => ({
      value: m.id, label: shortModel(m.id), hint: m.free ? "free" : (m.provider || "") }))];
  const effortOpts = [
    { value: "low", label: "Low effort", hint: "Fast + cheap · QA off" },
    { value: "default", label: "Default effort", hint: "Balanced routing" },
    { value: "high", label: "High effort", hint: "More budget · QA on" }];

  const box = (
    <div className="relative w-full bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-[26px] shadow-sm p-2.5 focus-within:border-accent-terracotta/40 focus-within:shadow-md transition-all">
      {/* Voice status: obvious feedback that the mic is live / transcribing. */}
      {micState !== "off" && (
        <div className={`flex items-center gap-2 px-3 pt-1 pb-2 text-[12px] font-medium ${micState === "recording" ? "text-red-500" : "text-accent-terracotta"}`}>
          {micState === "recording" ? (
            <>
              <span className="flex items-end gap-[3px] h-4" aria-hidden="true">
                {[0, 1, 2, 3].map((i) => <span key={i} className="vbar" style={{ animationDelay: `${i * 0.13}s` }} />)}
              </span>
              <span>Listening… <span className="text-light-muted font-normal">click the mic to stop</span></span>
            </>
          ) : (
            <>
              <span className="material-symbols-outlined text-[16px] animate-spin">progress_activity</span>
              <span>Transcribing your voice…</span>
            </>
          )}
        </div>
      )}
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
      {/* /command menu — opens while typing a bare /command */}
      {cmdMatches.length > 0 && (
        <div className="absolute bottom-full left-2 mb-1 w-80 max-w-[calc(100vw-2rem)] max-h-56 overflow-y-auto scrollbar bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-xl shadow-xl z-30 p-1 fadeup">
          <p className="text-[9px] uppercase tracking-widest text-light-muted px-2 py-1">Commands</p>
          {cmdMatches.map((c) => (
            <button key={c.name} type="button" onMouseDown={(e) => { e.preventDefault(); pickCommand(c.name); }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left hover:bg-surface-container-low dark:hover:bg-dark-bg transition">
              <span className="material-symbols-outlined text-[15px] text-accent-terracotta">bolt</span>
              <span className="text-[12px] font-code shrink-0">/{c.name}</span>
              {c.argument_hint && <span className="text-[10px] text-light-muted font-code shrink-0">{c.argument_hint}</span>}
              {c.description && <span className="text-[11px] text-light-muted truncate ml-auto">{c.description}</span>}
            </button>
          ))}
        </div>
      )}
      {/* @file mention picker — opens when you type @ before the caret */}
      {mention && matches.length > 0 && (
        <div className="absolute bottom-full left-2 mb-1 w-72 max-w-[calc(100vw-2rem)] max-h-56 overflow-y-auto scrollbar bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-xl shadow-xl z-30 p-1 fadeup">
          <p className="text-[9px] uppercase tracking-widest text-light-muted px-2 py-1">Reference a file</p>
          {matches.map((p) => (
            <button key={p} type="button" onMouseDown={(e) => { e.preventDefault(); pickFile(p); }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left hover:bg-surface-container-low dark:hover:bg-dark-bg transition">
              <span className="material-symbols-outlined text-[15px] text-accent-terracotta">description</span>
              <span className="text-[12px] font-code truncate">{p}</span>
            </button>
          ))}
        </div>
      )}
      <textarea
        ref={taRef}
        value={text}
        onChange={onType}
        onKeyDown={(e) => {
          if (cmdMatches.length && (e.key === "Enter" || e.key === "Tab")) { e.preventDefault(); pickCommand(cmdMatches[0].name); return; }
          if (mention && matches.length && (e.key === "Enter" || e.key === "Tab")) { e.preventDefault(); pickFile(matches[0]); return; }
          if (mention && e.key === "Escape") { setMention(null); return; }
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(); }
        }}
        placeholder={placeholder}
        rows={1}
        className="w-full px-3 pt-2 pb-1 bg-transparent resize-none outline-none text-[15px] leading-6 min-h-[40px] placeholder-light-muted"
      />
      <div className="flex items-center justify-between px-1 pt-1.5 gap-2">
        {/* LEFT: attach + inline Mode/Model/Effort + run-options (advanced behind the sliders).
            NOTE: no overflow-* here — it would clip the upward-opening dropdowns. Wrap instead. */}
        <div className="flex flex-wrap items-center gap-1 min-w-0">
          <label title="Attach a file (added as context)"
            className="w-9 h-9 shrink-0 rounded-full text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg flex items-center justify-center transition cursor-pointer">
            <span className="material-symbols-outlined text-[22px]">add</span>
            <input type="file" className="hidden" onChange={(e) => {
              const f = e.target.files?.[0]; if (f) addAttachment(f); e.currentTarget.value = "";
            }} />
          </label>
          <BarSelect label="Mode" icon="edit_note" value={planFirst ? "plan" : "build"}
            options={modeOpts} onPick={(v) => setPlanFirst(v === "plan")} />
          <BarSelect label="Model" icon="memory" value={modelOverride}
            options={modelOpts} onPick={setModelOverride} />
          <BarSelect label="Effort" icon="speed" value={effort}
            options={effortOpts} onPick={(v) => setEffort(v as "low" | "default" | "high")} />
          <div className="relative shrink-0" ref={popRef}>
            <button onClick={() => setOpts(!opts)} title="Run options — approval, plan-first, QA, parallel, limits" aria-label="Run options"
              className={`flex items-center gap-1.5 h-9 px-3 rounded-full text-[12px] transition ${opts ? "bg-accent-terracotta/10 text-accent-terracotta" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg"}`}>
              <span className="material-symbols-outlined text-[18px]">tune</span>
              <span className="hidden sm:inline">Options</span>
            </button>
            {opts && <RunOptions onClose={() => setOpts(false)} onQueue={queue} canQueue={!!text.trim() && !running} />}
          </div>
        </div>
        {/* RIGHT: mic (voice input) + send / stop */}
        <div className="flex items-center gap-1 shrink-0">
          {micAvailable && !running && (
            <button onClick={toggleMic} type="button"
              title={micState === "recording" ? "Stop & transcribe" : micState === "transcribing" ? "Transcribing…" : "Speak your message"}
              aria-label="Voice input"
              className={`w-9 h-9 rounded-full flex items-center justify-center transition ${
                micState === "recording" ? "bg-red-500 text-white animate-pulse"
                : micState === "transcribing" ? "text-accent-terracotta"
                : "text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg"}`}>
              <span className={`material-symbols-outlined text-[20px] ${micState === "transcribing" ? "animate-spin" : ""}`}>
                {micState === "transcribing" ? "progress_activity" : micState === "recording" ? "stop" : "mic"}
              </span>
            </button>
          )}
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
