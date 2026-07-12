import { useEffect, useRef, useState } from "react";
import { useStore } from "../lib/store";

type Cmd = { id: string; label: string; icon: string; hint?: string; run: () => void };

// Claude-style ⌘K palette: search and run actions or jump to any chat.
export default function CommandPalette({ onClose, onOpenSettings, onOpenBench }:
  { onClose: () => void; onOpenSettings: () => void; onOpenBench: () => void }) {
  const { sessions, newSession, selectSession, toggleTheme, exportChat, commands, setDraft } = useStore();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { inputRef.current?.focus(); }, []);

  const base: Cmd[] = [
    { id: "new", label: "New chat", icon: "edit_square", hint: "⌘K", run: () => { newSession(); onClose(); } },
    { id: "settings", label: "Open settings", icon: "settings", run: () => { onOpenSettings(); } },
    { id: "theme", label: "Toggle light / dark", icon: "dark_mode", run: () => { toggleTheme(); onClose(); } },
    { id: "bench", label: "Open Model Lab", icon: "science", run: () => { onOpenBench(); } },
    { id: "export", label: "Export this chat", icon: "download", run: () => { exportChat(); onClose(); } },
  ];
  const cmds: Cmd[] = (commands || []).map((c) => ({
    id: "cmd_" + c.name, label: "/" + c.name, icon: "bolt", hint: c.description || "command",
    run: () => { setDraft("/" + c.name + " "); onClose(); },
  }));
  const sess: Cmd[] = sessions.map((s) => ({
    id: "s_" + s.id, label: s.title || "Untitled", icon: "chat_bubble", hint: "chat",
    run: () => { selectSession(s.id); onClose(); },
  }));
  const all = [...base, ...cmds, ...sess];
  const ql = q.trim().toLowerCase();
  const filtered = ql ? all.filter((c) => c.label.toLowerCase().includes(ql)) : all;
  const clamped = Math.min(sel, Math.max(0, filtered.length - 1));

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, filtered.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); filtered[clamped]?.run(); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center pt-[15vh] px-4 bg-black/30" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-2xl overflow-hidden fadeup">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-light-border dark:border-dark-border">
          <span className="material-symbols-outlined text-light-muted text-[20px]">search</span>
          <input ref={inputRef} value={q} onChange={(e) => { setQ(e.target.value); setSel(0); }} onKeyDown={onKey}
            placeholder="Search commands and chats…"
            className="flex-1 bg-transparent outline-none text-[15px] placeholder-light-muted" />
          <kbd className="text-[10px] text-light-muted border border-light-border dark:border-dark-border rounded px-1.5 py-0.5">esc</kbd>
        </div>
        <div className="max-h-[50vh] overflow-y-auto scrollbar py-1">
          {filtered.length === 0 && <div className="px-4 py-6 text-center text-sm text-light-muted">No matches</div>}
          {filtered.map((c, i) => (
            <button key={c.id} onClick={c.run} onMouseEnter={() => setSel(i)}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm transition ${i === clamped ? "bg-surface-container-low dark:bg-dark-bg" : ""}`}>
              <span className="material-symbols-outlined text-[18px] text-light-muted">{c.icon}</span>
              <span className="flex-1 truncate">{c.label}</span>
              {c.hint && <span className="text-[10px] uppercase tracking-wide text-light-muted shrink-0">{c.hint}</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
