import { useEffect, useState } from "react";
import { useStore } from "../lib/store";
import { getAuthToken, setAuthToken } from "../lib/api";

function Row({ label, children }: { label: string; children: any }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-light-border dark:border-dark-border">
      <span className="text-sm">{label}</span>
      {children}
    </div>
  );
}

export default function SettingsModal({ onClose }: { onClose: () => void }) {
  const { mode, setMode, maxUsd, maxIter, setLimit, strategy, theme, toggleTheme, spend, loadSpend } = useStore();
  const dark = theme === "dark";
  const [token, setToken] = useState(getAuthToken());
  const inp = "w-20 bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1 text-sm outline-none";
  useEffect(() => {
    loadSpend();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const num = (e: React.ChangeEvent<HTMLInputElement>, k: "maxUsd" | "maxIter") => {
    const n = parseFloat(e.target.value);
    if (!Number.isNaN(n)) setLimit(k, n);   // allow 0; don't snap back to a default
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-6" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Settings"
        className="w-full max-w-md bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-2xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-display text-lg font-semibold">Settings</h3>
          <button onClick={onClose} className="material-symbols-outlined text-light-muted hover:text-on-surface dark:hover:text-dark-text">close</button>
        </div>
        <Row label="Theme">
          <button onClick={toggleTheme} className="flex items-center gap-1.5 text-sm px-3 py-1 rounded-lg border border-light-border dark:border-dark-border hover:bg-surface-container-low dark:hover:bg-dark-bg">
            <span className="material-symbols-outlined text-[16px]">{dark ? "dark_mode" : "light_mode"}</span>{dark ? "Dark" : "Light"}
          </button>
        </Row>
        <Row label="Default approvals">
          <select value={mode} onChange={(e) => setMode(e.target.value as any)} className={inp + " w-28"}>
            <option value="auto">auto</option><option value="careful">careful</option><option value="trusted">trusted</option>
          </select>
        </Row>
        <Row label="Max cost per run ($)">
          <input type="number" min="0" step="0.05" value={maxUsd} onChange={(e) => num(e, "maxUsd")} className={inp} />
        </Row>
        <Row label="Max loops per run">
          <input type="number" min="1" value={maxIter} onChange={(e) => num(e, "maxIter")} className={inp} />
        </Row>
        <Row label="Model strategy">
          <span className="text-sm text-accent-terracotta">{strategy === "cheapest" ? "cost-first (auto)" : "fixed tiers"}</span>
        </Row>
        <Row label="Spent today">
          <span className="text-sm">
            ${(spend?.spent_today ?? 0).toFixed(4)}
            <span className="text-light-muted">{spend?.cap != null ? ` / $${spend.cap.toFixed(2)} cap` : " (no cap)"}</span>
          </span>
        </Row>
        <Row label="Access token">
          <input type="password" value={token} placeholder="(deployed only)"
            onChange={(e) => { setToken(e.target.value); setAuthToken(e.target.value); }}
            className={inp + " w-40"} />
        </Row>
        <p className="text-xs text-light-muted mt-4">
          Models, embeddings, search and connectors are configured in <code>config/models.yaml</code> and
          <code>.env</code> — see <code>docs/PLACEHOLDERS.md</code>. Shortcut: <b>Ctrl/⌘+K</b> = new chat.
        </p>
      </div>
    </div>
  );
}
