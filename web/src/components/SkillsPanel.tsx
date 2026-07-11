import { useEffect, useMemo, useState } from "react";
import { useStore } from "../lib/store";
import { api } from "../lib/api";

type Available = { name: string; synced: boolean; source: string };

export default function SkillsPanel() {
  const { skills, loadSkills, messages } = useStore();
  const [busy, setBusy] = useState<string>("");        // name currently toggling/syncing
  const [err, setErr] = useState<string>("");
  const [viewing, setViewing] = useState<string>("");  // skill whose body is expanded
  const [body, setBody] = useState<string>("");
  const [scan, setScan] = useState<any>(null);         // security scan for the viewed skill
  const [pendingForce, setPendingForce] = useState<string>(""); // risky skill awaiting override

  // Hub (browse + sync) state
  const [showHub, setShowHub] = useState(false);
  const [sources, setSources] = useState<any[]>([]);
  const [source, setSource] = useState<string>("");
  const [available, setAvailable] = useState<Available[]>([]);
  const [loadingAvail, setLoadingAvail] = useState(false);

  useEffect(() => { if (!skills.length) loadSkills(); }, []);

  const applied = useMemo(() => {
    const seen = new Set<string>();
    for (const m of messages)
      for (const ev of m.events || [])
        if (ev.type === "skill") for (const s of ev.skills || []) seen.add(s);
    return seen;
  }, [messages]);

  const guard = async (name: string, fn: () => Promise<any>) => {
    setBusy(name); setErr("");
    try { await fn(); await loadSkills(); }
    catch (e: any) { setErr(e?.message || String(e)); }
    finally { setBusy(""); }
  };

  const toggle = async (s: any, force = false) => {
    if (s.enabled) { guard(s.name, () => api.skillDisable(s.name)); return; }
    setBusy(s.name); setErr("");
    try { await api.skillEnable(s.name, force); await loadSkills(); }
    catch (e: any) {
      // 409 = the scan flagged it risky; offer an explicit override.
      if (e?.status === 409) setPendingForce(s.name);
      else setErr(e?.message || String(e));
    } finally { setBusy(""); }
  };

  const view = async (name: string) => {
    if (viewing === name) { setViewing(""); return; }
    setViewing(name); setBody(""); setScan(null);
    try {
      const v = await api.skillView(name);
      setBody(v?.body || "(empty)"); setScan(v?.scan || null);
    } catch (e: any) { setBody(`error: ${e?.message || e}`); }
  };

  const openHub = async () => {
    setShowHub(!showHub);
    if (!sources.length) {
      try {
        const s = await api.skillSources();
        setSources(s);
        if (s[0]) { setSource(s[0].name); browse(s[0].name); }
      } catch (e: any) { setErr(e?.message || String(e)); }
    }
  };

  const browse = async (src: string) => {
    setLoadingAvail(true); setErr("");
    try { setAvailable(await api.skillsAvailable(src)); }
    catch (e: any) { setErr(e?.message || String(e)); setAvailable([]); }
    finally { setLoadingAvail(false); }
  };

  const sync = (name: string) =>
    guard(name, () => api.skillSync(source, name).then(() => browse(source)));

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <h4 className="text-[11px] uppercase tracking-widest text-light-muted">Skills</h4>
        <div className="flex items-center gap-1">
          <button onClick={openHub} title="Add skills from GitHub"
            className={`p-1 rounded-md transition ${showHub ? "text-accent-terracotta" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text"}`}>
            <span className="material-symbols-outlined text-[16px]">add</span>
          </button>
          <button onClick={() => loadSkills()} title="Refresh"
            className="p-1 rounded-md text-light-muted hover:text-on-surface dark:hover:text-dark-text transition">
            <span className="material-symbols-outlined text-[16px]">refresh</span>
          </button>
        </div>
      </div>
      <p className="px-5 pb-3 text-[11px] leading-4 text-light-muted">
        Expert playbooks the team loads automatically when a task matches. Toggle one off to
        stop it being used. Synced skills arrive <b>disabled</b> — review, then enable.
      </p>
      {err && <div className="mx-4 mb-2 text-[11px] text-red-500 break-words">{err}</div>}

      {/* Add-from-GitHub hub */}
      {showHub && (
        <div className="mx-4 mb-3 rounded-xl border border-light-border dark:border-dark-border p-3 bg-surface-container-low dark:bg-dark-bg">
          <div className="flex items-center gap-2 mb-2">
            <select value={source}
              onChange={(e) => { setSource(e.target.value); browse(e.target.value); }}
              className="text-[11px] bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-md px-2 py-1 flex-1">
              {sources.map((s) => <option key={s.name} value={s.name}>{s.name} ({s.repo})</option>)}
            </select>
          </div>
          <div className="space-y-1 max-h-48 overflow-y-auto scrollbar">
            {loadingAvail && <div className="text-[11px] text-light-muted px-1">Loading…</div>}
            {!loadingAvail && available.length === 0 && (
              <div className="text-[11px] text-light-muted px-1">No skills found (or GitHub unreachable).</div>)}
            {available.map((a) => (
              <div key={a.name} className="flex items-center gap-2 text-[11px] px-1 py-0.5">
                <span className="font-code flex-1 truncate">{a.name}</span>
                {a.synced
                  ? <span className="text-[9px] uppercase text-light-muted">synced</span>
                  : <button disabled={busy === a.name} onClick={() => sync(a.name)}
                      className="text-[10px] px-2 py-0.5 rounded-md bg-accent-terracotta/15 text-accent-terracotta hover:bg-accent-terracotta/25 disabled:opacity-50">
                      {busy === a.name ? "…" : "sync"}
                    </button>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Installed skills */}
      <div className="px-4 space-y-2 overflow-y-auto scrollbar flex-1 min-h-0">
        {skills.length === 0 && <div className="text-light-muted text-xs px-1 py-2">No skills loaded.</div>}
        {skills.map((s) => {
          const on = applied.has(s.name);
          const enabled = s.enabled !== false;
          return (
            <div key={s.name}
              className={`border rounded-xl p-3 bg-white dark:bg-dark-surface transition ${on ? "border-accent-terracotta/60" : "border-light-border dark:border-dark-border"} ${enabled ? "" : "opacity-60"}`}>
              <div className="flex items-center gap-2 mb-1">
                <span className="material-symbols-outlined text-accent-terracotta text-[18px]">bolt</span>
                <h3 className="text-sm font-semibold flex-1 truncate font-code">{s.name}</h3>
                {s.risk && s.risk !== "safe" && (
                  <span title={`${s.findings} security finding(s)`}
                    className={`text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded-full font-bold ${s.risk === "risky" ? "bg-red-500/15 text-red-600 dark:text-red-400" : "bg-amber-500/15 text-amber-600 dark:text-amber-400"}`}>
                    {s.risk}
                  </span>
                )}
                {on && (
                  <span className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-accent-terracotta/15 text-accent-terracotta font-bold">
                    applied
                  </span>
                )}
                {/* enable/disable toggle */}
                <button disabled={busy === s.name} onClick={() => toggle(s)} title={enabled ? "Enabled — click to disable" : "Disabled — click to enable"}
                  className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded-full transition disabled:opacity-50 ${enabled ? "bg-green-500/15 text-green-600 dark:text-green-400" : "bg-light-muted/15 text-light-muted"}`}>
                  {busy === s.name ? "…" : enabled ? "on" : "off"}
                </button>
              </div>
              <p className="text-[11px] leading-4 text-on-surface-variant dark:text-light-muted line-clamp-4">
                {s.description}
              </p>
              {pendingForce === s.name && (
                <div className="mt-2 text-[10px] rounded-md border border-red-500/40 bg-red-500/5 p-2">
                  <p className="text-red-600 dark:text-red-400 mb-1.5">This skill has HIGH-risk findings. Review them below before enabling.</p>
                  <div className="flex gap-2">
                    <button onClick={() => { setPendingForce(""); toggle(s, true); }}
                      className="text-[10px] px-2 py-0.5 rounded-md bg-red-500/15 text-red-600 dark:text-red-400 font-bold">Override &amp; enable</button>
                    <button onClick={() => { setPendingForce(""); if (viewing !== s.name) view(s.name); }}
                      className="text-[10px] px-2 py-0.5 rounded-md bg-light-muted/15 text-light-muted">Review first</button>
                  </div>
                </div>
              )}
              <div className="flex items-center gap-2 mt-1.5">
                {s.source && <span className="text-[9px] text-light-muted font-code truncate">{s.source}</span>}
                <button onClick={() => view(s.name)}
                  className="text-[10px] text-light-muted hover:text-accent-terracotta ml-auto">
                  {viewing === s.name ? "hide" : "review"}
                </button>
              </div>
              {viewing === s.name && (
                <div className="mt-2">
                  {scan && scan.findings && scan.findings.length > 0 && (
                    <div className="mb-2 text-[10px] rounded-md bg-surface-container-low dark:bg-dark-bg p-2">
                      <p className="uppercase tracking-wide text-light-muted mb-1">Security scan · {scan.risk}</p>
                      {scan.findings.map((f: any, i: number) => (
                        <div key={i} className="flex gap-1.5 py-0.5">
                          <span className={f.severity === "high" ? "text-red-500" : "text-amber-500"}>●</span>
                          <span className="font-code truncate flex-1" title={f.snippet}>{f.file}:{f.line}</span>
                          <span className="text-light-muted truncate">{f.why}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <pre className="text-[10px] leading-4 whitespace-pre-wrap break-words max-h-56 overflow-y-auto scrollbar bg-surface-container-low dark:bg-dark-bg rounded-md p-2 text-on-surface-variant dark:text-light-muted">
                    {body || "…"}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
