import { useEffect, useState } from "react";
import { useStore } from "../lib/store";
import { api } from "../lib/api";

// Friendly countdown from an ISO timestamp ("in 2h 14m" / "due now").
function countdown(iso: string): string {
  if (!iso) return "";
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso);
  const ms = new Date(hasTz ? iso : iso + "Z").getTime() - Date.now();
  if (isNaN(ms)) return "";
  if (ms <= 0) return "due now";
  const s = Math.round(ms / 1000), d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `in ${d}d ${h}h`;
  if (h) return `in ${h}h ${m}m`;
  return m ? `in ${m}m` : `in ${s}s`;
}

const KINDS = [
  { id: "daily", label: "Daily", spec: "09:00", hint: "HH:MM (UTC)" },
  { id: "weekly", label: "Weekly", spec: "0 09:00", hint: "DOW HH:MM (0=Mon)" },
  { id: "interval", label: "Every N seconds", spec: "3600", hint: "seconds" },
  { id: "once", label: "Once", spec: "", hint: "ISO datetime (UTC)" },
];

const SUGGESTIONS = [
  { icon: "summarize", title: "Morning briefing", desc: "A short brief each morning of what needs your attention.", kind: "daily", spec: "08:00", text: "Give me a concise morning briefing of the most important updates." },
  { icon: "lightbulb", title: "Content ideas", desc: "Draft a few post ideas each week from the latest in your field.", kind: "weekly", spec: "0 09:00", text: "Draft 3 post ideas from the latest developments in AI agents, with sources." },
  { icon: "checklist", title: "Weekly review", desc: "A Friday summary of what happened this week.", kind: "weekly", spec: "4 16:00", text: "Summarize what happened this week and what's pending." },
  { icon: "travel_explore", title: "Monitor a topic", desc: "Watch for news or mentions of a topic, competitor, or keyword.", kind: "daily", spec: "09:00", text: "Search for the latest news on a topic I care about and summarize anything new." },
];

export default function ScheduledView() {
  const { sessions } = useStore();
  const [list, setList] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [text, setText] = useState("");
  const [kind, setKind] = useState("daily");
  const [spec, setSpec] = useState("09:00");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => { try { setList(await api.schedules()); } catch { /* empty */ } };
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);

  const titleOf = (s: any) => sessions.find((x: any) => x.id === s.session_id)?.title || s.text?.slice(0, 60) || "Scheduled task";
  const shown = q.trim() ? list.filter((s) => (titleOf(s) + " " + (s.text || "")).toLowerCase().includes(q.toLowerCase())) : list;

  const pickKind = (k: string) => { setKind(k); setSpec(KINDS.find((x) => x.id === k)?.spec || ""); };
  const useSuggestion = (s: typeof SUGGESTIONS[0]) => { setText(s.text); setKind(s.kind); setSpec(s.spec); setShowNew(true); };

  const create = async () => {
    if (!text.trim()) { setMsg("Describe the task to run."); return; }
    setBusy(true); setMsg("");
    try {
      const sess = await api.createSession(text.trim().slice(0, 48));   // a dedicated session for the task
      await api.createSchedule({ session_id: sess.id, text: text.trim(), kind, spec });
      setText(""); setShowNew(false); load();
    } catch (e: any) { setMsg(e.message || "could not create the task"); }
    finally { setBusy(false); }
  };
  const toggle = async (id: string) => { try { await api.toggleSchedule(id); load(); } catch { /* */ } };
  const runNow = async (id: string) => { try { await api.runSchedule(id); load(); } catch { /* */ } };
  const del = async (id: string) => { if (confirm("Delete this scheduled task?")) { try { await api.deleteSchedule(id); load(); } catch { /* */ } } };

  const field = "w-full bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent-terracotta";

  return (
    <div className="flex-1 overflow-y-auto scrollbar px-gutter py-8">
      <div className="max-w-[880px] mx-auto">
        <div className="flex items-start justify-between gap-4 mb-1">
          <h2 className="font-headline text-[28px] font-semibold tracking-tight">Scheduled tasks</h2>
          <button onClick={() => { setShowNew((o) => !o); setMsg(""); }}
            className="shrink-0 flex items-center gap-2 px-4 py-2 rounded-xl bg-accent-terracotta hover:bg-accent-deep text-white text-[13px] font-medium transition">
            <span className="material-symbols-outlined text-[18px]">add</span> New task
          </button>
        </div>
        <p className="text-[13px] text-light-muted mb-5">
          Run tasks on a schedule, or whenever you need them. They run on the server — even when your computer is off.
        </p>

        {/* search */}
        <div className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl border border-light-border dark:border-dark-border bg-white dark:bg-dark-surface mb-4">
          <span className="material-symbols-outlined text-[19px] text-light-muted">search</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search scheduled tasks…"
            className="flex-1 bg-transparent outline-none text-sm placeholder-light-muted" />
        </div>

        {/* new task form */}
        {showNew && (
          <div className="border border-light-border dark:border-dark-border rounded-2xl bg-white dark:bg-dark-surface p-4 mb-5 fadeup">
            <label className="text-[11px] uppercase tracking-widest text-light-muted">Task</label>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2}
              placeholder="e.g. Summarize the latest issues in my repo and suggest fixes."
              className={field + " mt-1 mb-3 resize-none"} />
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label className="text-[11px] uppercase tracking-widest text-light-muted">Repeat</label>
                <select value={kind} onChange={(e) => pickKind(e.target.value)} className={field + " mt-1 w-44"}>
                  {KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
                </select>
              </div>
              <div className="flex-1 min-w-[160px]">
                <label className="text-[11px] uppercase tracking-widest text-light-muted">When <span className="normal-case tracking-normal text-light-muted">· {KINDS.find((k) => k.id === kind)?.hint}</span></label>
                <input value={spec} onChange={(e) => setSpec(e.target.value)} className={field + " mt-1"} />
              </div>
              <button onClick={create} disabled={busy}
                className="px-4 py-2 rounded-xl bg-accent-terracotta hover:bg-accent-deep text-white text-[13px] font-medium disabled:opacity-50">
                {busy ? "Creating…" : "Create task"}
              </button>
            </div>
            {msg && <p className="text-[12px] text-red-500 mt-2">{msg}</p>}
          </div>
        )}

        {/* list or empty */}
        {shown.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14 text-center">
            <span className="material-symbols-outlined text-[52px] text-light-muted mb-3">schedule</span>
            <p className="text-[14px] text-light-muted">{q.trim() ? "No tasks match." : "No scheduled tasks yet."}</p>
          </div>
        ) : (
          <div className="space-y-2 mb-4">
            {shown.map((s) => (
              <div key={s.id} className="flex items-center gap-3 border border-light-border dark:border-dark-border rounded-xl bg-white dark:bg-dark-surface px-4 py-3">
                <span className={`material-symbols-outlined text-[20px] ${s.enabled ? "text-accent-terracotta" : "text-light-muted"}`}>schedule</span>
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] font-medium truncate">{titleOf(s)}</div>
                  <div className="text-[11.5px] text-light-muted font-code">
                    {s.kind} · {s.spec} {s.next_run && <>· {countdown(s.next_run)}</>} {!s.enabled && "· paused"}
                  </div>
                </div>
                <button onClick={() => runNow(s.id)} title="Run now" className="p-1.5 rounded-lg text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg"><span className="material-symbols-outlined text-[18px]">play_arrow</span></button>
                <button onClick={() => toggle(s.id)} title={s.enabled ? "Pause" : "Resume"} className="p-1.5 rounded-lg text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg"><span className="material-symbols-outlined text-[18px]">{s.enabled ? "pause" : "play_circle"}</span></button>
                <button onClick={() => del(s.id)} title="Delete" className="p-1.5 rounded-lg text-light-muted hover:text-red-500"><span className="material-symbols-outlined text-[18px]">delete</span></button>
              </div>
            ))}
          </div>
        )}

        {/* suggested */}
        <div className="relative my-8 h-px bg-light-border dark:bg-dark-border" />
        <p className="text-[11px] uppercase tracking-widest text-light-muted font-semibold mb-3">Try one of these</p>
        <div className="grid sm:grid-cols-2 gap-3">
          {SUGGESTIONS.map((s) => (
            <button key={s.title} onClick={() => useSuggestion(s)}
              className="text-left flex gap-3 border border-light-border dark:border-dark-border rounded-xl bg-white dark:bg-dark-surface p-4 hover:border-accent-terracotta transition">
              <span className="material-symbols-outlined text-[20px] text-accent-terracotta shrink-0">{s.icon}</span>
              <div className="min-w-0">
                <div className="text-[13.5px] font-semibold">{s.title}</div>
                <div className="text-[12px] text-light-muted mt-0.5">{s.desc}</div>
                <div className="text-[11px] text-light-muted font-code mt-1.5 flex items-center gap-1">
                  <span className="material-symbols-outlined text-[13px]">schedule</span>{s.kind} · {s.spec}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
