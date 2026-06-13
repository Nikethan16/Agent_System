import { useEffect, useState } from "react";
import { useStore } from "../lib/store";
import { getAuthToken, setAuthToken } from "../lib/api";
import ModelRail from "./ModelRail";
import MemoryPanel from "./MemoryPanel";
import FleetPanel from "./FleetPanel";
import HealthPanel from "./HealthPanel";
import SchedulesPanel from "./SchedulesPanel";
import RoadmapPanel from "./RoadmapPanel";

const TABS = [
  { id: "general", label: "General", icon: "tune" },
  { id: "limits", label: "Limits & cost", icon: "savings" },
  { id: "models", label: "Models", icon: "smart_toy" },
  { id: "fleet", label: "Fleet & keys", icon: "key" },
  { id: "health", label: "Model health", icon: "monitoring" },
  { id: "schedules", label: "Schedules", icon: "schedule" },
  { id: "roadmap", label: "Roadmap", icon: "checklist" },
  { id: "memory", label: "Memory", icon: "neurology" },
  { id: "security", label: "Security", icon: "shield" },
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
  const [token, setToken] = useState(getAuthToken());
  const inp = "bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1 text-sm outline-none";

  useEffect(() => {
    loadSpend();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Load memory data when its tab is first opened.
  useEffect(() => { if (tab === "memory") { loadFacts(); loadRules(); } }, [tab]);

  const num = (e: React.ChangeEvent<HTMLInputElement>, k: "maxUsd" | "maxIter") => {
    const n = parseFloat(e.target.value); if (!Number.isNaN(n)) setLimit(k, n);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-4 md:p-6" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Settings"
        className="w-full max-w-3xl h-[600px] max-h-[88vh] bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-2xl flex overflow-hidden" onClick={(e) => e.stopPropagation()}>
        {/* Left nav */}
        <div className="w-44 md:w-52 shrink-0 border-r border-light-border dark:border-dark-border p-3 bg-surface-container-low dark:bg-dark-bg/40 flex flex-col">
          <h3 className="font-display text-lg font-semibold px-2 mb-4">Settings</h3>
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-2.5 py-2 rounded-lg text-sm text-left transition mb-0.5 ${tab === t.id ? "bg-white dark:bg-dark-surface text-accent-terracotta font-medium shadow-sm" : "text-on-surface-variant dark:text-light-muted hover:bg-surface-container dark:hover:bg-dark-surface"}`}>
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
                <p className="text-xs text-light-muted mt-4">Shortcut: <b>Ctrl/⌘+K</b> = new chat. Slash commands: <code>/new /export /model /mode /help</code>.</p>
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
                <p className="text-xs text-light-muted mt-4">The daily spend cap is set with <code>AGENT_DAILY_USD_CAP</code> in <code>.env</code>.</p>
              </div>
            )}
            {tab === "models" && (
              <div>
                <div className="flex items-center justify-between gap-3 mb-3">
                  <div>
                    <div className="text-sm font-medium">Model selection</div>
                    <div className="text-[11px] text-light-muted">Strategy: {strategy === "cheapest" ? "cost-first (auto-picks cheapest capable model)" : "fixed per-tier"}</div>
                  </div>
                  {onOpenBench && (
                    <button onClick={onOpenBench} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-light-border dark:border-dark-border hover:bg-surface-container-low dark:hover:bg-dark-bg shrink-0">
                      <span className="material-symbols-outlined text-[16px]">science</span>Model Lab
                    </button>
                  )}
                </div>
                <ModelRail />
              </div>
            )}
            {tab === "fleet" && <FleetPanel />}
            {tab === "health" && <HealthPanel />}
            {tab === "schedules" && <SchedulesPanel />}
            {tab === "roadmap" && <RoadmapPanel />}
            {tab === "memory" && <MemoryPanel />}
            {tab === "security" && (
              <div>
                <Row label="Access token" hint="Only needed when hosting off this machine.">
                  <input type="password" value={token} placeholder="(deployed only)"
                    onChange={(e) => { setToken(e.target.value); setAuthToken(e.target.value); }} className={inp + " w-44"} />
                </Row>
                <p className="text-xs text-light-muted mt-4">Embeddings, search and connectors are configured in <code>.env</code> / <code>config/</code> — see <code>docs/PLACEHOLDERS.md</code>.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
