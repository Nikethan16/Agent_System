import { useEffect } from "react";

const SHORTCUTS: { keys: string[]; label: string }[] = [
  { keys: ["⌘/Ctrl", "K"], label: "Command palette / search" },
  { keys: ["⌘/Ctrl", "⇧", "O"], label: "New chat" },
  { keys: ["⌘/Ctrl", "\\"], label: "Toggle workspace panel" },
  { keys: ["Enter"], label: "Send message" },
  { keys: ["⇧", "Enter"], label: "New line" },
  { keys: ["/"], label: "Slash commands (in the box)" },
  { keys: ["Esc"], label: "Close dialogs / canvas" },
  { keys: ["?"], label: "Show this help" },
];

export default function ShortcutsOverlay({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-sm bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-2xl p-5 pop" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 mb-3">
          <span className="material-symbols-outlined text-accent-terracotta text-[20px]">keyboard</span>
          <h2 className="font-semibold flex-1">Keyboard shortcuts</h2>
          <button onClick={onClose} aria-label="Close" className="material-symbols-outlined text-[18px] text-light-muted hover:text-on-surface dark:hover:text-dark-text">close</button>
        </div>
        <div className="space-y-2">
          {SHORTCUTS.map((s, i) => (
            <div key={i} className="flex items-center justify-between gap-3 text-[13px]">
              <span className="text-on-surface-variant dark:text-light-muted">{s.label}</span>
              <span className="flex items-center gap-1 shrink-0">
                {s.keys.map((k, j) => (
                  <kbd key={j} className="font-code text-[11px] px-1.5 py-0.5 rounded-md bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border">{k}</kbd>
                ))}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
