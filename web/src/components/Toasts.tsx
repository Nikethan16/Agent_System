import { useStore } from "../lib/store";

// Transient notices (errors, budget/loop limits) so they don't clutter the thread.
export default function Toasts() {
  const { toasts, dismissToast } = useStore();
  if (!toasts.length) return null;
  return (
    <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[70] flex flex-col items-center gap-2 pointer-events-none px-4 w-full max-w-md">
      {toasts.map((t) => {
        const cls = t.kind === "error"
          ? "border-red-300 dark:border-red-900 text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/50"
          : t.kind === "success"
          ? "border-emerald-300 dark:border-emerald-900 text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/50"
          : "border-light-border dark:border-dark-border bg-white dark:bg-dark-surface text-on-surface dark:text-dark-text";
        const icon = t.kind === "error" ? "error" : t.kind === "success" ? "check_circle" : "info";
        return (
          <div key={t.id} className={`pointer-events-auto flex items-center gap-2 w-full px-4 py-2.5 rounded-xl border shadow-lg text-sm fadeup ${cls}`}>
            <span className="material-symbols-outlined text-[18px] shrink-0">{icon}</span>
            <span className="flex-1 break-words">{t.text}</span>
            <button onClick={() => dismissToast(t.id)} aria-label="Dismiss" className="material-symbols-outlined text-[16px] opacity-60 hover:opacity-100 shrink-0">close</button>
          </div>
        );
      })}
    </div>
  );
}
