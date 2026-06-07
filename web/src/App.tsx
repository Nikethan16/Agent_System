import { useEffect, useState } from "react";
import { useStore } from "./lib/store";
import Sidebar from "./components/Sidebar";
import Chat from "./components/Chat";
import Composer from "./components/Composer";
import RightPanel from "./components/RightPanel";
import SettingsModal from "./components/SettingsModal";
import BenchmarkModal from "./components/BenchmarkModal";

export default function App() {
  const { init, connected, running, cost, newSession } = useStore();
  const [settings, setSettings] = useState(false);
  const [bench, setBench] = useState(false);
  const [leftOpen, setLeftOpen] = useState(false);   // mobile sidebar drawer
  const [rightOpen, setRightOpen] = useState(false);  // mobile right panel drawer
  useEffect(() => { init(); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); newSession(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="h-screen overflow-hidden text-on-surface dark:text-dark-text">
      <Sidebar open={leftOpen} onClose={() => setLeftOpen(false)} />
      {/* Mobile backdrop when a drawer is open */}
      {(leftOpen || rightOpen) && (
        <div className="fixed inset-0 bg-black/30 z-30 md:hidden"
             onClick={() => { setLeftOpen(false); setRightOpen(false); }} />
      )}
      <main className="md:ml-sidebar-width md:mr-panel-width h-screen flex flex-col bg-surface dark:bg-dark-bg">
        <header className="h-14 px-gutter flex items-center justify-between border-b border-light-border dark:border-dark-border bg-surface/80 dark:bg-dark-bg/80 backdrop-blur sticky top-0 z-10">
          <div className="flex items-center gap-3">
            <button onClick={() => setLeftOpen(true)} title="Menu"
              className="md:hidden text-light-muted hover:text-on-surface dark:hover:text-dark-text">
              <span className="material-symbols-outlined text-[22px]">menu</span>
            </button>
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-widest font-semibold text-light-muted">
              <span className={`w-2 h-2 rounded-full ${running ? "bg-accent-terracotta animate-pulse" : connected ? "bg-emerald-500" : "bg-light-muted"}`} />
              {running ? "Working" : connected ? "Backend Live" : "Offline"}
            </div>
          </div>
          <div className="flex items-center gap-5">
            <div className="text-right">
              <div className="text-[9px] uppercase tracking-widest text-light-muted leading-none">Run cost</div>
              <div className="text-sm font-semibold">$<span className="text-accent-terracotta">{cost.toFixed(4)}</span></div>
            </div>
            <button onClick={() => setSettings(true)} title="Settings" aria-label="Settings" className="text-light-muted hover:text-on-surface dark:hover:text-dark-text">
              <span className="material-symbols-outlined text-[20px]">settings</span>
            </button>
            <button onClick={() => setRightOpen(true)} title="Artifacts & panels"
              className="md:hidden text-light-muted hover:text-on-surface dark:hover:text-dark-text">
              <span className="material-symbols-outlined text-[22px]">dashboard</span>
            </button>
          </div>
        </header>
        <Chat />
        <Composer />
      </main>
      <RightPanel open={rightOpen} onClose={() => setRightOpen(false)} />
      {settings && <SettingsModal onClose={() => setSettings(false)} onOpenBench={() => { setSettings(false); setBench(true); }} />}
      {bench && <BenchmarkModal onClose={() => setBench(false)} />}
    </div>
  );
}
