import { useEffect, useState } from "react";
import { useStore } from "../lib/store";
import { api } from "../lib/api";

const inp =
  "bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1 text-sm outline-none";

const SPEC_HINT: Record<string, string> = {
  once: "ISO datetime, e.g. 2026-06-20T09:00:00 (UTC)",
  interval: "seconds between runs, e.g. 3600",
  daily: "HH:MM (UTC), e.g. 09:00",
  weekly: "DOW HH:MM (0=Mon..6=Sun), e.g. 0 09:00",
};

// "in 2h 14m" / "in 45s" / "due now" — a friendlier read than a bare UTC timestamp.
function countdown(iso: string): string {
  if (!iso) return "";
  // Backend may emit either a bare datetime or one with a tz offset (+00:00 / Z).
  // Only stamp UTC when there's no tz info at all — appending Z to "+00:00" is invalid.
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso);
  const ms = new Date(hasTz ? iso : iso + "Z").getTime() - Date.now();
  if (isNaN(ms)) return "";
  if (ms <= 0) return "due now";
  const s = Math.round(ms / 1000);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `in ${d}d ${h}h`;
  if (h) return `in ${h}h ${m}m`;
  if (m) return `in ${m}m`;
  return `in ${s}s`;
}

const STATUS_COLOR: Record<string, string> = {
  done: "text-emerald-500", error: "text-red-500",
  running: "text-accent-terracotta", queued: "text-amber-500",
};

// Settings → Schedules: run a saved task on a schedule, in the current chat.
export default function SchedulesPanel() {
  const currentId = useStore((s) => s.currentId);
  const [list, setList] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [kind, setKind] = useState("daily");
  const [spec, setSpec] = useState("09:00");
  const [msg, setMsg] = useState("");

  const load = async () => { try { setList(await api.schedules()); } catch { /* empty */ } };
  useEffect(() => {
    load();
    const t = setInterval(load, 15000);   // refresh status + countdown while open
    return () => clearInterval(t);
  }, []);

  const create = async () => {
    if (!currentId) { setMsg("Open a chat first — the scheduled task runs inside it."); return; }
    if (!text.trim()) { setMsg("Enter a task to run."); return; }
    setMsg("");
    try { await api.createSchedule({ session_id: currentId, text: text.trim(), kind, spec }); setText(""); load(); }
    catch (e: any) { setMsg(e.message); }
  };
  const toggle = async (id: string) => { try { await api.toggleSchedule(id); load(); } catch (e: any) { setMsg(e.message); } };
  const runNow = async (id: string) => { try { await api.runSchedule(id); setMsg("queued a run"); load(); } catch (e: any) { setMsg(e.message); } };
  const del = async (id: string) => { try { await api.deleteSchedule(id); load(); } catch (e: any) { setMsg(e.message); } };

  return (
    <div className="space-y-4">
      <div className="text-[11px] text-light-muted">
        Scheduled tasks run unattended in the chosen chat via the job queue (auto-approve path;
        risky actions are still policy-gated). Times are UTC. They survive restarts.
      </div>

      <div className="rounded-lg border border-light-border dark:border-dark-border p-3 space-y-2">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="task to run, e.g. summarize today's news on AI agents"
          className={inp + " w-full"} />
        <div className="flex items-center gap-2">
          <select value={kind} onChange={(e) => { setKind(e.target.value); setSpec(""); }} className={inp}>
            <option value="once">once</option><option value="interval">interval</option>
            <option value="daily">daily</option><option value="weekly">weekly</option>
          </select>
          <input value={spec} onChange={(e) => setSpec(e.target.value)} placeholder={SPEC_HINT[kind]} className={inp + " flex-1"} />
          <button onClick={create} className="text-sm px-3 py-1 rounded-lg bg-accent-terracotta text-white">Add</button>
        </div>
        <div className="text-[10px] text-light-muted">{SPEC_HINT[kind]}</div>
      </div>

      {list.length === 0 && <div className="text-xs text-light-muted">No schedules yet.</div>}
      {list.map((s) => (
        <div key={s.id} className="flex items-center justify-between gap-2 text-xs py-2 border-b border-light-border dark:border-dark-border">
          <div className="min-w-0">
            <div className="truncate">{s.text}</div>
            <div className="text-[10px] text-light-muted">
              {s.kind} {s.spec} · {s.enabled
                ? <>next {(s.next_run_at || "").replace("T", " ").slice(0, 16)} UTC{countdown(s.next_run_at) && <span className="text-on-surface dark:text-dark-text"> ({countdown(s.next_run_at)})</span>}</>
                : "disabled"}
            </div>
            {s.last_status && (
              <div className="text-[10px] text-light-muted">
                last run: <span className={STATUS_COLOR[s.last_status] || ""}>{s.last_status}</span>
                {s.last_result && <span title={s.last_result}> · {s.last_result.slice(0, 48)}{s.last_result.length > 48 ? "…" : ""}</span>}
              </div>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button onClick={() => runNow(s.id)} title="run now" className="material-symbols-outlined text-[16px] text-light-muted hover:text-accent-terracotta">play_arrow</button>
            <button onClick={() => toggle(s.id)} title="enable/disable" className="material-symbols-outlined text-[16px] text-light-muted hover:text-on-surface">{s.enabled ? "pause" : "resume"}</button>
            <button onClick={() => del(s.id)} title="delete" className="material-symbols-outlined text-[16px] text-light-muted hover:text-red-500">delete</button>
          </div>
        </div>
      ))}
      {msg && <div className="text-[11px] text-light-muted">{msg}</div>}
    </div>
  );
}
