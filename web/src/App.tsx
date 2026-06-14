import { useEffect, useRef, useState } from "react";
import { useStore } from "./lib/store";
import { api, setAuthToken } from "./lib/api";
import Login from "./components/Login";
import Sidebar from "./components/Sidebar";
import Chat from "./components/Chat";
import Composer from "./components/Composer";
import RightPanel from "./components/RightPanel";
import SettingsModal from "./components/SettingsModal";
import BenchmarkModal from "./components/BenchmarkModal";
import CommandPalette from "./components/CommandPalette";
import Toasts from "./components/Toasts";
import Sunburst from "./components/Sunburst";

const SUGGESTIONS = [
  { icon: "code", label: "Write & run code", prompt: "Write a Python function to check if a number is prime, then run it on a few examples." },
  { icon: "travel_explore", label: "Research a topic", prompt: "Research the top 3 trends in AI agents for 2026 and summarize them with sources." },
  { icon: "description", label: "Draft a document", prompt: "Draft a one-page project brief for a small task-tracking web app." },
  { icon: "table_chart", label: "Make a spreadsheet", prompt: "Create a simple monthly budget spreadsheet with categories, amounts, and a total." },
];

function timeGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

// The Claude-style welcome: a centered serif greeting with the composer right below it
// and a few example chips. Shown only when the conversation is empty.
function WelcomeScreen() {
  const { submit } = useStore();
  return (
    <div className="flex-1 overflow-y-auto scrollbar flex flex-col items-center justify-center px-gutter">
      <div className="w-full max-w-[720px] -mt-12 pb-8">
        <div className="flex items-center justify-center gap-3 mb-8">
          <Sunburst size={30} />
          <h2 className="font-body-prose text-[30px] md:text-[36px] leading-none text-on-surface dark:text-dark-text">{timeGreeting()}</h2>
        </div>
        <Composer variant="center" />
        <div className="flex flex-wrap gap-2 justify-center mt-5">
          {SUGGESTIONS.map((s) => (
            <button key={s.label} onClick={() => submit(s.prompt)}
              className="flex items-center gap-2 text-[13px] px-3.5 py-2 rounded-full border border-light-border dark:border-dark-border bg-white/50 dark:bg-dark-surface/50 hover:bg-white dark:hover:bg-dark-surface hover:border-accent-terracotta/40 transition text-on-surface-variant dark:text-light-muted">
              <span className="material-symbols-outlined text-[18px] text-accent-terracotta">{s.icon}</span>{s.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const { init, connected, running, cost, messages, files } = useStore();
  const [settings, setSettings] = useState(false);
  const [bench, setBench] = useState(false);
  const [palette, setPalette] = useState(false);      // ⌘K command palette
  const [leftOpen, setLeftOpen] = useState(false);    // mobile sidebar drawer
  const [rightOpen, setRightOpen] = useState(false);  // artifacts panel (desktop + mobile)
  const [auth, setAuth] = useState<"checking" | "login" | "in">("checking");
  const [email, setEmail] = useState("");
  const hasMessages = messages.length > 0;

  // Decide whether to show the login screen: skip it when login isn't enabled on
  // the server; otherwise verify the stored token via /api/me.
  useEffect(() => {
    let cancel = false;
    api.authConfig()
      .then((cfg) => {
        if (cancel) return;
        if (!cfg.login_enabled) { setAuth("in"); return; }
        api.me()
          .then((r) => { if (!cancel) { setEmail(r.email || ""); setAuth("in"); } })
          .catch(() => { if (!cancel) setAuth("login"); });
      })
      .catch(() => { if (!cancel) setAuth("in"); });   // config unreachable -> don't lock out
    return () => { cancel = true; };
  }, []);

  // Load the app only once we're past the gate.
  useEffect(() => { if (auth === "in") init(); }, [auth]);

  const logout = () => { setAuthToken(""); setEmail(""); setAuth("login"); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Auto-open the artifacts panel the first time the agent produces a file.
  const prevFiles = useRef(0);
  useEffect(() => {
    if (files.length > prevFiles.current && files.length > 0) setRightOpen(true);
    prevFiles.current = files.length;
  }, [files.length]);

  // Keep the artifacts panel out of the way on the empty welcome screen.
  useEffect(() => {
    if (!hasMessages) setRightOpen(false);
  }, [hasMessages]);

  if (auth === "checking") {
    return (
      <div className="h-screen flex items-center justify-center bg-surface dark:bg-dark-bg">
        <Sunburst size={36} className="animate-pulse" />
      </div>
    );
  }
  if (auth === "login") {
    return <Login onSuccess={(em) => { setEmail(em); setAuth("in"); }} />;
  }

  return (
    <div className="h-screen overflow-hidden text-on-surface dark:text-dark-text">
      <Sidebar open={leftOpen} onClose={() => setLeftOpen(false)}
        email={email} onOpenSettings={() => setSettings(true)} onLogout={logout} />
      {/* Mobile backdrop when a drawer is open */}
      {(leftOpen || rightOpen) && (
        <div className="fixed inset-0 bg-black/30 z-30 md:hidden"
             onClick={() => { setLeftOpen(false); setRightOpen(false); }} />
      )}
      <main className={`md:ml-sidebar-width h-screen flex flex-col bg-surface dark:bg-dark-bg transition-[margin] duration-200 ${rightOpen ? "md:mr-panel-width" : ""}`}>
        <header className="h-14 px-gutter flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <button onClick={() => setLeftOpen(true)} title="Menu"
              className="md:hidden text-light-muted hover:text-on-surface dark:hover:text-dark-text">
              <span className="material-symbols-outlined text-[22px]">menu</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-light-muted">
              <span className={`w-1.5 h-1.5 rounded-full ${running ? "bg-accent-terracotta animate-pulse" : connected ? "bg-emerald-500" : "bg-light-muted"}`} />
              {running ? "Working…" : connected ? "Connected" : "Offline"}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {cost > 0 && (
              <span className="text-[11px] text-light-muted mr-1">${cost.toFixed(4)}</span>
            )}
            <button onClick={() => setRightOpen(!rightOpen)} title="Artifacts & panels" aria-label="Toggle artifacts panel"
              className={`relative p-2 rounded-lg transition ${rightOpen ? "bg-surface-container-high dark:bg-dark-surface text-on-surface dark:text-dark-text" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-surface"}`}>
              <span className="material-symbols-outlined text-[20px]">dock_to_left</span>
              {files.length > 0 && <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-accent-terracotta" />}
            </button>
            <button onClick={() => setSettings(true)} title="Settings" aria-label="Settings"
              className="p-2 rounded-lg text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-surface transition">
              <span className="material-symbols-outlined text-[20px]">settings</span>
            </button>
          </div>
        </header>
        {hasMessages ? (
          <>
            <Chat />
            <Composer variant="bottom" />
          </>
        ) : (
          <WelcomeScreen />
        )}
      </main>
      <RightPanel open={rightOpen} onClose={() => setRightOpen(false)} />
      {settings && <SettingsModal onClose={() => setSettings(false)} onOpenBench={() => { setSettings(false); setBench(true); }} />}
      {bench && <BenchmarkModal onClose={() => setBench(false)} />}
      {palette && <CommandPalette
        onClose={() => setPalette(false)}
        onOpenSettings={() => { setPalette(false); setSettings(true); }}
        onOpenBench={() => { setPalette(false); setBench(true); }} />}
      <Toasts />
    </div>
  );
}
