import { useEffect, useState } from "react";
import { api } from "../lib/api";

// Per-use-case model routing editor: for each task type, order the model chain (primary
// first) from the catalog. Saved to data/routing.json (server-side) — no code/YAML edit,
// survives deploys. A chain the model falls DOWN when the primary is rate-limited/down.

type Cat = { id: string; free: boolean; available: boolean; requires_env: string | null; good_for: string[] };

const USE_CASE_HELP: Record<string, string> = {
  coding: "Writing & running code (the build tier).",
  planning: "The lead's plan for a complex task.",
  reasoning: "Hard reasoning / the tier-3 lead loop.",
  math: "Math-heavy tasks.",
  qa: "The critic — reviews & runs tests.",
  review: "Code review.",
  research: "Web research & tool-calling.",
  data: "Data analysis (code that computes).",
  chat: "Quick chat / short replies.",
  general: "General assistant answers.",
  writing: "Prose & documents.",
  classify: "The router (task → tier/type).",
  frontend: "UI / HTML / React builds.",
  vision: "Image understanding.",
};

export default function RoutingEditor() {
  const [routing, setRouting] = useState<Record<string, string[]>>({});
  const [defaults, setDefaults] = useState<Record<string, string[]>>({});
  const [customized, setCustomized] = useState<string[]>([]);
  const [catalog, setCatalog] = useState<Cat[]>([]);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  const load = async () => {
    setErr("");
    try {
      const r = await api.getRouting();
      setRouting(r.routing || {}); setDefaults(r.defaults || {});
      setCustomized(r.customized || []); setCatalog(r.catalog || []);
    } catch (e: any) { setErr(e?.message || String(e)); }
  };
  useEffect(() => { load(); }, []);

  const save = async (t: string, chain: string[]) => {
    setBusy(t); setErr("");
    try { const r = await api.setRouting(t, chain); setRouting(r.routing); setCustomized((c) => c.includes(t) ? c : [...c, t]); }
    catch (e: any) { setErr(e?.message || String(e)); }
    finally { setBusy(""); }
  };
  const reset = async (t: string) => {
    setBusy(t); setErr("");
    try { const r = await api.resetRouting(t); setRouting(r.routing); setCustomized((c) => c.filter((x) => x !== t)); }
    catch (e: any) { setErr(e?.message || String(e)); }
    finally { setBusy(""); }
  };

  const move = (t: string, i: number, d: -1 | 1) => {
    const chain = [...(routing[t] || [])]; const j = i + d;
    if (j < 0 || j >= chain.length) return;
    [chain[i], chain[j]] = [chain[j], chain[i]]; save(t, chain);
  };
  const remove = (t: string, id: string) => save(t, (routing[t] || []).filter((m) => m !== id));
  const add = (t: string, id: string) => { if (id && !(routing[t] || []).includes(id)) save(t, [...(routing[t] || []), id]); };

  const shortId = (id: string) => id.split("/").slice(-1)[0];
  const useCases = Object.keys(routing).sort();

  return (
    <div className="space-y-3">
      <p className="text-[11px] text-light-muted">
        Choose which model serves each use case, and its fallback order (primary first; the
        run falls down the list if a model is rate-limited or down). Saved instantly; a key-less
        model is skipped at run time. Edits persist across restarts &amp; deploys.
      </p>
      {err && <div className="text-[11px] text-red-500 break-words">{err}</div>}

      {useCases.map((t) => {
        const chain = routing[t] || [];
        const isCustom = customized.includes(t);
        const addable = catalog.filter((c) => !chain.includes(c.id));
        return (
          <div key={t} className="border border-light-border dark:border-dark-border rounded-xl p-3 bg-white dark:bg-dark-surface">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-sm font-semibold font-code">{t}</h3>
              {isCustom && <span className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-accent-terracotta/15 text-accent-terracotta font-bold">customized</span>}
              {isCustom && (
                <button disabled={busy === t} onClick={() => reset(t)}
                  className="ml-auto text-[10px] text-light-muted hover:text-accent-terracotta">reset to default</button>
              )}
            </div>
            {USE_CASE_HELP[t] && <p className="text-[10px] text-light-muted mb-2">{USE_CASE_HELP[t]}</p>}

            <div className="space-y-1">
              {chain.map((id, i) => {
                const meta = catalog.find((c) => c.id === id);
                const off = meta && !meta.available;
                return (
                  <div key={id} className={`flex items-center gap-2 text-[11px] px-2 py-1 rounded-md bg-surface-container-low dark:bg-dark-bg ${off ? "opacity-50" : ""}`}>
                    <span className="text-[9px] text-light-muted w-4">{i === 0 ? "1st" : i + 1}</span>
                    <span className="font-code flex-1 truncate" title={id}>{shortId(id)}</span>
                    {meta?.free && <span className="text-[8px] uppercase text-green-600 dark:text-green-400">free</span>}
                    {off && <span className="text-[8px] uppercase text-amber-500" title={`needs ${meta?.requires_env}`}>no key</span>}
                    <button disabled={busy === t || i === 0} onClick={() => move(t, i, -1)} className="text-light-muted hover:text-on-surface disabled:opacity-30" title="up">
                      <span className="material-symbols-outlined text-[14px]">arrow_upward</span></button>
                    <button disabled={busy === t || i === chain.length - 1} onClick={() => move(t, i, 1)} className="text-light-muted hover:text-on-surface disabled:opacity-30" title="down">
                      <span className="material-symbols-outlined text-[14px]">arrow_downward</span></button>
                    <button disabled={busy === t} onClick={() => remove(t, id)} className="text-light-muted hover:text-red-500" title="remove">
                      <span className="material-symbols-outlined text-[14px]">close</span></button>
                  </div>
                );
              })}
              {chain.length === 0 && <div className="text-[10px] text-light-muted px-2 py-1">Empty — auto-picks by cost. Add a model to pin it.</div>}
            </div>

            <select value="" disabled={busy === t} onChange={(e) => add(t, e.target.value)}
              className="mt-2 w-full text-[11px] bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-md px-2 py-1">
              <option value="">+ add a fallback model…</option>
              {addable.map((c) => (
                <option key={c.id} value={c.id}>{shortId(c.id)}{c.free ? " (free)" : ""}{!c.available ? " — no key" : ""}</option>
              ))}
            </select>
          </div>
        );
      })}
      {useCases.length === 0 && !err && <div className="text-xs text-light-muted">Loading…</div>}
    </div>
  );
}
