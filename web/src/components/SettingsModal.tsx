import { useEffect, useState } from "react";
import { useStore } from "../lib/store";
import { getAuthToken, setAuthToken } from "../lib/api";
import ModelRail from "./ModelRail";
import RoutingEditor from "./RoutingEditor";
import MemoryPanel from "./MemoryPanel";
import FleetPanel from "./FleetPanel";
import HealthPanel from "./HealthPanel";
import SchedulesPanel from "./SchedulesPanel";
import UsagePanel from "./UsagePanel";

// Clear homes — every feature lives in exactly one (the old build had drifted to 9).
const TABS = [
  { id: "general", label: "General", icon: "tune" },
  { id: "limits", label: "Limits & cost", icon: "savings" },
  { id: "usage", label: "Usage & cost", icon: "monitoring" },
  { id: "models", label: "Models & keys", icon: "smart_toy" },
  { id: "memory", label: "Memory", icon: "neurology" },
  { id: "advanced", label: "Advanced", icon: "shield" },
];

// "Models & keys" gathers everything model-related (was 3 separate tabs).
const MODEL_SUBS = [
  { id: "tiers", label: "Tiers" },
  { id: "routing", label: "Routing" },
  { id: "keys", label: "Keys & fleet" },
  { id: "health", label: "Health" },
];

function Row({ label, hint, children }: { label: string; hint?: string; children: any }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-b border-light-border dark:border-dark-border">
      <div>
        <div className="text-sm">{label}</div>
        {hint && <div className="text-[11px] text-light-muted mt-0.5">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

export default function SettingsModal({ onClose, onOpenBench }: { onClose: () => void; onOpenBench?: () => void }) {
  const { mode, setMode, maxUsd, maxIter, setLimit, strategy, theme, toggleTheme, spend, loadSpend, exportChat,
          loadFacts, loadRules } = useStore();
  const dark = theme === "dark";
  const [tab, setTab] = useState("general");
  const [modelSub, setModelSub] = useState("tiers");
  const [token, setToken] = useState(getAuthToken());
  const inp = "bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1 text-sm outline-none";

  // Run ONCE when the modal opens. Depending on [onClose] re-fired this effect on
  // every App re-render (onClose is a fresh closure each render) — during a streaming
  // run that hammered /api/spend hundreds of times a minute and tripped the rate
  // limiter, breaking the whole UI. loadSpend is a one-shot; the keydown closure
  // captures a stable setSettings, so [] is correct.
  useEffect(() => {
    loadSpend();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load memory data when its tab is first opened.
  useEffect(() => { if (tab === "memory") { loadFacts(); loadRules(); } }, [tab]);

  const num = (e: React.ChangeEvent<HTMLInputElement>, k: "maxUsd" | "maxIter") => {
    const n = parseFloat(e.target.value); if (!Number.isNaN(n)) setLimit(k, n);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 md:p-6" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Settings"
        className="w-full max-w-3xl h-[600px] max-h-[88vh] bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-2xl flex overflow-hidden" onClick={(e) => e.stopPropagation()}>
        {/* Left nav */}
        <div className="w-44 md:w-52 shrink-0 border-r border-light-border dark:border-dark-border p-3 bg-claude-sidebar dark:bg-dark-bg/40 flex flex-col">
          <h3 className="font-headline text-lg font-semibold px-2 mb-4">Settings</h3>
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-2.5 py-2 rounded-lg text-sm text-left transition mb-0.5 ${tab === t.id ? "bg-white dark:bg-dark-surface text-accent-terracotta font-medium shadow-sm" : "text-on-surface-variant dark:text-light-muted hover:bg-white/60 dark:hover:bg-dark-surface"}`}>
              <span className="material-symbols-outlined text-[18px]">{t.icon}</span>{t.label}
            </button>
          ))}
        </div>
        {/* Content */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex items-center justify-end p-3 border-b border-light-border dark:border-dark-border">
            <button onClick={onClose} aria-label="Close settings" className="material-symbols-outlined text-light-muted hover:text-on-surface dark:hover:text-dark-text">close</button>
          </div>
          <div className="flex-1 overflow-y-auto scrollbar p-5">
            {tab === "general" && (
              <div>
                <Row label="Theme">
                  <button onClick={toggleTheme} className="flex items-center gap-1.5 text-sm px-3 py-1 rounded-lg border border-light-border dark:border-dark-border hover:bg-surface-container-low dark:hover:bg-dark-bg">
                    <span className="material-symbols-outlined text-[16px]">{dark ? "dark_mode" : "light_mode"}</span>{dark ? "Dark" : "Light"}
                  </button>
                </Row>
                <Row label="Default approvals" hint="The default; override per run in the composer's Run options.">
                  <select value={mode} onChange={(e) => setMode(e.target.value as any)} className={inp + " w-28"}>
                    <option value="auto">auto</option><option value="careful">careful</option><option value="trusted">trusted</option>
                  </select>
                </Row>
                <Row label="Export this chat" hint="Download the conversation as Markdown.">
                  <button onClick={exportChat} className="flex items-center gap-1.5 text-sm px-3 py-1 rounded-lg border border-light-border dark:border-dark-border hover:bg-surface-container-low dark:hover:bg-dark-bg">
                    <span className="material-symbols-outlined text-[16px]">download</span>Export
                  </button>
                </Row>
                <p className="text-xs text-light-muted mt-4">Shortcut: <b>Ctrl/⌘+K</b> = command palette. Slash commands: <code>/new /export /model /mode /help</code>.</p>
              </div>
            )}
            {tab === "limits" && (
              <div>
                <Row label="Default max cost per run ($)">
                  <input type="number" min="0" step="0.05" value={maxUsd} onChange={(e) => num(e, "maxUsd")} className={inp + " w-24"} />
                </Row>
                <Row label="Default max loops per run">
                  <input type="number" min="1" value={maxIter} onChange={(e) => num(e, "maxIter")} className={inp + " w-24"} />
                </Row>
                <Row label="Spent today">
                  <span className="text-sm">${(spend?.spent_today ?? 0).toFixed(4)}
                    <span className="text-light-muted">{spend?.cap != null ? ` / $${spend.cap.toFixed(2)} cap` : " (no cap)"}</span></span>
                </Row>
                <p className="text-xs text-light-muted mt-4">The daily spend cap is set with <code>AGENT_DAILY_USD_CAP</code> in <code>.env</code>. See <b>Usage &amp; cost</b> for trends.</p>
              </div>
            )}
            {tab === "usage" && <UsagePanel />}
            {tab === "models" && (
              <div>
                <div className="flex items-center justify-between gap-3 mb-4">
                  <div className="flex items-center bg-surface-container-low dark:bg-dark-bg p-1 rounded-xl">
                    {MODEL_SUBS.map((s) => (
                      <button key={s.id} onClick={() => setModelSub(s.id)}
                        className={`px-3 py-1 text-xs rounded-lg transition ${modelSub === s.id ? "bg-white dark:bg-dark-surface shadow-sm font-medium" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text"}`}>{s.label}</button>
                    ))}
                  </div>
                  {onOpenBench && (
                    <button onClick={onOpenBench} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-light-border dark:border-dark-border hover:bg-surface-container-low dark:hover:bg-dark-bg shrink-0">
                      <span className="material-symbols-outlined text-[16px]">science</span>Model Lab
                    </button>
                  )}
                </div>
                {modelSub === "tiers" && (
                  <div>
                    <div className="text-[11px] text-light-muted mb-3">Strategy: {strategy === "cheapest" ? "cost-first (auto-picks cheapest capable model)" : "fixed per-tier"}</div>
                    <ModelRail />
                  </div>
                )}
                {modelSub === "routing" && <RoutingEditor />}
                {modelSub === "keys" && <FleetPanel />}
                {modelSub === "health" && <HealthPanel />}
              </div>
            )}
            {tab === "memory" && <MemoryPanel />}
            {tab === "advanced" && (
              <div className="space-y-6">
                <div>
                  <p className="text-[11px] uppercase tracking-widest text-light-muted mb-2">Security</p>
                  <Row label="Access token" hint="Only needed when hosting off this machine.">
                    <input type="password" value={token} placeholder="(deployed only)"
                      onChange={(e) => { setToken(e.target.value); setAuthToken(e.target.value); }} className={inp + " w-44"} />
                  </Row>
                  <p className="text-xs text-light-muted mt-3">Embeddings, search and connectors are configured in <code>.env</code> / <code>config/</code> — see <code>docs/PLACEHOLDERS.md</code>.</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-widest text-light-muted mb-2">Scheduled tasks</p>
                  <SchedulesPanel />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
