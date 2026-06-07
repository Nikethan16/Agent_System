import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

// Model Lab — score a model on a fixed task battery (concrete pass/fail per aspect),
// in raw (model only) and/or pipeline (model + orchestration) mode, and compare
// models side-by-side to pick the right one per task.
const ASPECTS = ["coding", "reasoning", "writing", "instruction"];
const ASPECT_LABEL: Record<string, string> = {
  coding: "Coding", reasoning: "Reason", writing: "Writing", instruction: "Format",
};

function pct(s: any) {
  if (!s || !s.total) return "—";
  return `${s.passed}/${s.total}`;
}

function ScoreCells({ scores, mode }: { scores: any; mode: string }) {
  const m = scores?.[mode];
  return (
    <>
      {ASPECTS.map((a) => {
        const s = m?.[a];
        const ratio = s && s.total ? s.passed / s.total : null;
        const color = ratio == null ? "text-light-muted"
          : ratio >= 0.7 ? "text-emerald-600 dark:text-emerald-400"
          : ratio >= 0.4 ? "text-amber-600 dark:text-amber-400" : "text-red-500";
        return <td key={a} className={`px-2 py-1.5 text-center text-xs font-code ${color}`}>{pct(s)}</td>;
      })}
    </>
  );
}

export default function BenchmarkModal({ onClose }: { onClose: () => void }) {
  const [cases, setCases] = useState<any>({ aspects: {}, models: [], modes: ["both"] });
  const [runs, setRuns] = useState<any[]>([]);
  const [model, setModel] = useState("");
  const [mode, setMode] = useState("both");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const poll = useRef<any>(null);

  const load = async () => { try { setRuns(await api.benchmarkRuns()); } catch (e: any) { setErr(e?.message || String(e)); } };

  useEffect(() => {
    (async () => {
      try {
        const c = await api.benchmarkCases();
        setCases(c);
        if (c.models?.length) setModel(c.models[0]);
      } catch (e: any) { setErr(e?.message || String(e)); }
    })();
    load();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); if (poll.current) clearInterval(poll.current); };
  }, [onClose]);

  // poll while any run is in progress
  useEffect(() => {
    const anyRunning = runs.some((r) => r.status === "running");
    if (anyRunning && !poll.current) poll.current = setInterval(load, 3000);
    if (!anyRunning && poll.current) { clearInterval(poll.current); poll.current = null; }
  }, [runs]);

  const run = async () => {
    if (!model.trim()) return;
    setBusy(true); setErr("");
    try { await api.startBenchmark(model.trim(), mode); await load(); }
    catch (e: any) { setErr(e?.message || String(e)); }
    finally { setBusy(false); }
  };

  const totalTasks = Object.values(cases.aspects || {}).reduce((a: number, b: any) => a + b, 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-6" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Model Lab"
        className="w-full max-w-3xl max-h-[85vh] bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-2xl flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-light-border dark:border-dark-border">
          <div>
            <h3 className="font-display text-lg font-semibold">Model Lab</h3>
            <p className="text-[11px] text-light-muted">Score models on {String(totalTasks)} pass/fail tasks across {ASPECTS.length} aspects, then compare.</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="material-symbols-outlined text-light-muted hover:text-on-surface dark:hover:text-dark-text">close</button>
        </div>

        {/* run controls */}
        <div className="px-6 py-3 border-b border-light-border dark:border-dark-border flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wide text-light-muted">Model</span>
            <input list="bench-models" value={model} onChange={(e) => setModel(e.target.value)} placeholder="model id"
              className="w-64 text-sm bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1.5 outline-none" />
            <datalist id="bench-models">
              {(cases.models || []).map((m: string) => <option key={m} value={m} />)}
            </datalist>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wide text-light-muted">Mode</span>
            <select value={mode} onChange={(e) => setMode(e.target.value)}
              className="text-sm bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1.5 outline-none">
              <option value="both">raw + pipeline</option>
              <option value="raw">raw (model only)</option>
              <option value="pipeline">pipeline (model + orchestration)</option>
            </select>
          </label>
          <button onClick={run} disabled={busy || !model.trim()}
            className="px-4 py-2 bg-accent-terracotta text-white text-sm rounded-lg hover:brightness-110 active:scale-95 transition disabled:opacity-40">
            {busy ? "Starting…" : "Run benchmark"}
          </button>
          <span className="text-[11px] text-light-muted">Runs real model calls (cost-capped). One at a time.</span>
        </div>

        {err && <div className="px-6 py-2 text-xs text-red-500">⚠️ {err}</div>}

        {/* results / compare table */}
        <div className="flex-1 overflow-auto scrollbar p-4">
          {runs.length === 0 ? (
            <div className="text-light-muted text-sm px-2 py-6 text-center">No benchmarks yet. Pick a model and run one.</div>
          ) : (
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-light-muted border-b border-light-border dark:border-dark-border">
                  <th className="px-2 py-1.5 text-left">Model</th>
                  <th className="px-2 py-1.5 text-left">Run</th>
                  {ASPECTS.map((a) => <th key={a} className="px-2 py-1.5 text-center">{ASPECT_LABEL[a]}</th>)}
                  <th className="px-2 py-1.5 text-right">Cost</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => {
                  const modesShown = r.mode === "both" ? ["raw", "pipeline"] : [r.mode];
                  return modesShown.map((md, i) => (
                    <tr key={r.id + md} className="border-b border-light-border/50 dark:border-dark-border">
                      {i === 0 && (
                        <td rowSpan={modesShown.length} className="px-2 py-1.5 align-top font-code text-xs break-all max-w-[180px]">
                          {r.model}
                          {r.status === "running" && <span className="ml-1 text-accent-terracotta animate-pulse">●</span>}
                          {r.status === "error" && <div className="text-[10px] text-red-500 mt-0.5">{r.error}</div>}
                        </td>
                      )}
                      <td className="px-2 py-1.5 text-[10px] uppercase tracking-wide text-light-muted">{md}</td>
                      <ScoreCells scores={r.result?.scores} mode={md} />
                      {i === 0 && <td rowSpan={modesShown.length} className="px-2 py-1.5 text-right align-top text-xs font-code">${(r.cost || 0).toFixed(4)}</td>}
                    </tr>
                  ));
                })}
              </tbody>
            </table>
          )}
        </div>
        <div className="px-6 py-3 border-t border-light-border dark:border-dark-border text-[11px] text-light-muted">
          Scores are tasks passed / total per aspect (concrete pass/fail — not a rating). Green ≥70%, amber ≥40%, red below.
        </div>
      </div>
    </div>
  );
}
