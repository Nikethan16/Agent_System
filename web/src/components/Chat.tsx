import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore, type Msg, type Ev } from "../lib/store";
import { CodeBlock } from "./CodeBlock";
import { Mermaid } from "./Mermaid";

const MD = {
  code({ className, children, ...props }: any) {
    const m = /language-(\w+)/.exec(className || "");
    const text = String(children).replace(/\n$/, "");
    if (m?.[1] === "mermaid") return <Mermaid code={text} />;
    if (m || text.includes("\n")) return <CodeBlock lang={m?.[1]} code={text} />;
    return <code {...props}>{children}</code>;
  },
};

const PILL: Record<string, string> = {
  route: "bg-blue-100 text-blue-700",
  plan: "bg-amber-100 text-amber-700",
  assign: "bg-emerald-100 text-emerald-700",
  thought: "bg-surface-container-highest text-on-surface-variant",
  tool: "bg-accent-terracotta/10 text-accent-terracotta",
  fallback: "bg-amber-100 text-amber-700",
  retry: "bg-amber-100 text-amber-700",
  manager_review: "bg-red-100 text-red-700",
  critic: "bg-blue-100 text-blue-700",
  memory: "bg-emerald-100 text-emerald-700",
  skill: "bg-purple-100 text-purple-700",
  blocked: "bg-red-100 text-red-700",
  denied: "bg-red-100 text-red-700",
  error: "bg-red-100 text-red-700",
};

function describe(ev: Ev): { label: string; text: any } | null {
  switch (ev.type) {
    case "route": return { label: "Router", text: <>classified <b>tier {ev.tier}</b> · {ev.task_type} — {ev.reason}</> };
    case "plan": return { label: "Planner", text: `${ev.subtasks?.length} subtasks: ${ev.subtasks?.join("  →  ")}` };
    case "assign": return { label: ev.label || ev.agent, text: <>{ev.subtask ? ev.subtask : "handling task"} <span className="text-light-muted">· {ev.model}</span></> };
    case "thought": return { label: ev.agent, text: (ev.text || "").slice(0, 280) };
    case "tool": return { label: "Tool", text: <code className="font-code text-[12px]">{ev.name}({Object.entries(ev.args || {}).map(([k, v]) => `${k}=${JSON.stringify(v).slice(0, 40)}`).join(", ")})</code> };
    case "fallback": return { label: "Fallback", text: <><b>{(ev.from || "").split("/").pop()}</b> unavailable → <b>{(ev.to || "").split("/").pop()}</b> <span className="text-light-muted">· {ev.reason}</span></> };
    case "retry": return { label: "Retry", text: <>retrying <b>{ev.agent}</b> <span className="text-light-muted">· {ev.reason}</span></> };
    case "manager_review": return { label: "Security", text: <>{ev.approved ? "approved" : "denied"} — {ev.reason}</> };
    case "critic": return { label: "QA", text: <><b>{ev.passed ? "pass" : "fail"}</b> — {ev.summary}</> };
    case "memory": return { label: "Memory", text: `recalled ${ev.items?.length} note(s) from past chats` };
    case "skill": return { label: "Skill", text: <>applied skill{ev.skills?.length > 1 ? "s" : ""}: <b>{(ev.skills || []).join(", ")}</b></> };
    case "blocked": case "denied": return { label: ev.type, text: `${ev.name}: ${ev.reason}` };
    case "error": case "limit": case "stopping": return { label: "System", text: ev.text || "stopping…" };
    default: return null;
  }
}

const MEANINGFUL = ["plan", "tool", "critic", "manager_review", "memory", "skill", "blocked", "denied", "fallback", "retry"];

const FIXABLE = ["error", "blocked", "denied", "limit"];

// At-a-glance: a compact chip per sub-agent showing what it's doing right now
// (running / retrying / done) — like Claude's agent strip, without the full timeline.
function AgentStatus({ events, running }: { events: Ev[]; running?: boolean }) {
  const order: string[] = [];
  const status: Record<string, string> = {};
  for (const e of events) {
    const a = (e as any).agent;
    if (e.type === "assign" && a) { if (!order.includes(a)) order.push(a); status[a] = "running"; }
    else if (e.type === "retry" && a) status[a] = "retrying";
    else if (e.type === "done" && a) status[a] = "done";
  }
  const finalized = !running && events.some((e) => e.type === "final");
  const chips = order.filter((a) => a !== "lead");
  if (!chips.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5 px-3 py-2 border-b border-light-border/40 dark:border-dark-border">
      {chips.map((a) => {
        const s = finalized && status[a] !== "retrying" ? "done" : status[a];
        const cls = s === "done" ? "bg-emerald-100 text-emerald-700"
          : s === "retrying" ? "bg-amber-100 text-amber-700"
          : "bg-accent-terracotta/10 text-accent-terracotta";
        const dot = s === "done" ? "✓" : s === "retrying" ? "↻" : "●";
        return (
          <span key={a} className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full ${cls}`}>
            <span className={s === "running" ? "animate-pulse" : ""}>{dot}</span>{a}
            {s === "running" ? " · working" : s === "retrying" ? " · retrying" : ""}
          </span>
        );
      })}
    </div>
  );
}

function Activity({ events, running }: { events: Ev[]; running?: boolean }) {
  const { submit } = useStore();
  const [open, setOpen] = useState(false);   // collapsed by default — keep the chat clean
  const steps = events.map(describe).map((d, i) => ({ d, ev: events[i] })).filter((x) => x.d);
  // Only surface the timeline when the team actually did work (tools, a plan, QA, etc.),
  // or while a run is in progress. Simple Q&A turns show nothing.
  const worthShowing = events.some((e) => MEANINGFUL.includes(e.type)) ||
    events.filter((e) => e.type === "assign").length > 1 || running;
  if (!steps.length || !worthShowing) return null;
  return (
    <div className="mt-3 border border-light-border dark:border-dark-border rounded-xl overflow-hidden">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between px-3 py-2 hover:bg-surface-container-low dark:hover:bg-dark-bg/50 transition">
        <div className="flex items-center gap-2 text-light-muted">
          <span className={`w-1.5 h-1.5 rounded-full ${running ? "bg-accent-terracotta animate-pulse" : "bg-light-muted"}`} />
          <span className="text-[11px] uppercase tracking-wide">Agent activity · {steps.length} steps</span>
        </div>
        <span className="material-symbols-outlined text-light-muted text-[16px]">{open ? "expand_less" : "expand_more"}</span>
      </button>
      <AgentStatus events={events} running={running} />
      {open && (
        <div className="px-5 pb-5 pt-3 border-t border-light-border/40 dark:border-dark-border">
          <div className="space-y-4 relative before:absolute before:left-[5px] before:top-2 before:bottom-2 before:w-px before:bg-light-border dark:before:bg-dark-border">
            {steps.map(({ d, ev }, i) => (
              <div key={i} className="relative pl-6 fadeup">
                <span className="absolute left-0 top-1.5 w-[11px] h-[11px] rounded-full bg-white dark:bg-dark-surface border-2 border-light-border dark:border-dark-border" />
                <div className="flex items-center gap-2 mb-0.5">
                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-tight ${PILL[ev.type] || "bg-surface-container text-on-surface-variant"}`}>{d!.label}</span>
                </div>
                <div className="text-xs text-on-surface-variant dark:text-light-muted">{d!.text}</div>
                {FIXABLE.includes(ev.type) && !running && (
                  <button onClick={() => submit(`The previous attempt hit an error: "${ev.reason || ev.text || ev.name}". Please diagnose and fix it, then try again.`)}
                    className="mt-1 text-[10px] uppercase tracking-wide text-accent-terracotta hover:brightness-110 flex items-center gap-1">
                    <span className="material-symbols-outlined text-[13px]">build</span> Try fixing
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function UserMessage({ m, index }: { m: Msg; index: number }) {
  const { editMessage, running } = useStore();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(m.content);
  if (editing) {
    return (
      <div className="fadeup">
        <div className="bg-white dark:bg-dark-surface border border-accent-terracotta/40 rounded-2xl p-3">
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus rows={2}
            className="w-full bg-transparent resize-none outline-none text-[15px]" />
          <div className="flex justify-end gap-2 mt-1">
            <button onClick={() => setEditing(false)} className="text-[11px] uppercase tracking-wide text-light-muted px-2 py-1">Cancel</button>
            <button onClick={() => { setEditing(false); editMessage(index, draft); }}
              className="text-[11px] uppercase tracking-wide bg-accent-terracotta text-white rounded-lg px-3 py-1">Send</button>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="group flex items-start gap-2 fadeup">
      <div className="flex-1 bg-surface-container dark:bg-dark-surface rounded-2xl px-5 py-3.5">
        <p className="text-[15px] whitespace-pre-wrap leading-7">{m.content}</p>
      </div>
      {!running && (
        <button onClick={() => { setDraft(m.content); setEditing(true); }} title="Edit & branch"
          className="material-symbols-outlined text-[16px] text-light-muted hover:text-on-surface dark:hover:text-dark-text opacity-0 group-hover:opacity-100 mt-3 shrink-0">edit</button>
      )}
    </div>
  );
}

function Message({ m, index, isLast }: { m: Msg; index: number; isLast?: boolean }) {
  if (m.role === "user") return <UserMessage m={m} index={index} />;
  return (
    <div className="fadeup group">
      {m.content ? (
        <div className="prose-msg text-on-surface dark:text-dark-text">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>{m.content}</ReactMarkdown>
          {m.pending && <span className="caret" />}
        </div>
      ) : m.pending && !m.live ? (
        <div className="flex items-center gap-2 text-light-muted text-sm">
          <span className="w-1.5 h-1.5 rounded-full bg-accent-terracotta animate-pulse" /> Thinking…
        </div>
      ) : null}
      {m.live ? (
        <div className="mt-2 rounded-xl border border-light-border dark:border-dark-border bg-surface-container-low dark:bg-dark-bg/60 px-3 py-2">
          <div className="flex items-center gap-1.5 mb-1 text-[9px] uppercase tracking-widest text-accent-terracotta font-bold">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-terracotta animate-pulse" /> streaming
          </div>
          <div className="font-code text-[12px] leading-5 text-on-surface-variant dark:text-light-muted whitespace-pre-wrap">{m.live}<span className="caret" /></div>
        </div>
      ) : null}
      {m.events.length > 0 && <Activity events={m.events} running={m.pending} />}
      {m.content && !m.pending && <ResponseFooter m={m} last={isLast} />}
    </div>
  );
}

const fmtDur = (ms?: number) => {
  if (!ms || ms < 0) return null;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const mins = Math.floor(s / 60);
  return `${mins}m ${Math.round(s - mins * 60)}s`;
};

// Claude Code-style run summary (time · tokens · cost · tools · files edited) plus the
// always-visible response actions (copy / regenerate / feedback).
function ResponseFooter({ m, last }: { m: Msg; last?: boolean }) {
  const { regenerate, running, sendFeedback } = useStore();
  const [copied, setCopied] = useState(false);
  const [fb, setFb] = useState("");
  const copy = () => { navigator.clipboard?.writeText(m.content); setCopied(true); setTimeout(() => setCopied(false), 1200); };
  const btn = "p-1.5 rounded-md text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg transition";

  const tools = m.events.filter((e) => e.type === "tool");
  const meta = m.meta;
  // Prefer backend-computed per-file +/- line counts; fall back to tool-event paths
  // (older messages predate the run_complete `files` payload).
  const fileChanges = meta?.files && meta.files.length
    ? meta.files
    : (() => {
        const set = new Set<string>();
        for (const e of tools) {
          if (["write_file", "edit_file", "create_file"].includes(e.name) && e.args?.path) set.add(e.args.path);
        }
        return [...set].map((path) => ({ path, status: "", added: 0, removed: 0 }));
      })();
  const dur = fmtDur(meta?.durationMs);

  const stats: string[] = [];
  if (dur) stats.push(dur);
  if (meta?.tokens) stats.push(`${meta.tokens.toLocaleString()} tokens`);
  if (meta?.cost) stats.push(`$${meta.cost.toFixed(4)}`);
  if (tools.length) stats.push(`${tools.length} tool${tools.length > 1 ? "s" : ""}`);

  return (
    <div className="mt-2.5 space-y-1.5">
      {(stats.length > 0 || fileChanges.length > 0) && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-light-muted">
          {stats.length > 0 && (
            <span className="inline-flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[13px] text-emerald-500">check_circle</span>
              {stats.join(" · ")}
            </span>
          )}
          {fileChanges.map((f) => (
            <span key={f.path} className="inline-flex items-center gap-1">
              <span className="material-symbols-outlined text-[13px]">draft</span>
              <code className="font-code text-[10px] bg-surface-container dark:bg-dark-bg rounded px-1 py-0.5">{f.path}</code>
              {(f.added > 0 || f.removed > 0) && (
                <span className="font-code text-[10px]">
                  {f.added > 0 && <span className="text-emerald-500">+{f.added}</span>}
                  {f.added > 0 && f.removed > 0 && " "}
                  {f.removed > 0 && <span className="text-red-500">−{f.removed}</span>}
                </span>
              )}
            </span>
          ))}
        </div>
      )}
      <div className="flex items-center gap-0.5 -ml-1.5">
        <button onClick={copy} title="Copy" className={btn}><span className="material-symbols-outlined text-[16px]">{copied ? "check" : "content_copy"}</span></button>
        {last && (
          <button onClick={() => !running && regenerate()} title="Regenerate" className={btn} disabled={running}>
            <span className="material-symbols-outlined text-[16px]">refresh</span>
          </button>
        )}
        <button onClick={() => { setFb("up"); sendFeedback("up"); }} title="Good response" className={btn}>
          <span className="material-symbols-outlined text-[16px]" style={fb === "up" ? { fontVariationSettings: "'FILL' 1", color: "#16a34a" } : undefined}>thumb_up</span>
        </button>
        <button onClick={() => { setFb("down"); sendFeedback("down"); }} title="Bad response" className={btn}>
          <span className="material-symbols-outlined text-[16px]" style={fb === "down" ? { fontVariationSettings: "'FILL' 1", color: "#dc2626" } : undefined}>thumb_down</span>
        </button>
      </div>
    </div>
  );
}

function PlanCard() {
  const { pendingPlan, runPlan, running } = useStore();
  if (!pendingPlan || running) return null;
  return (
    <div className="fadeup">
      <div className="border border-accent-terracotta/40 bg-accent-terracotta/5 rounded-2xl p-4">
        <p className="text-[11px] uppercase tracking-widest font-bold text-accent-terracotta mb-2">▶ Plan ready</p>
        <ol className="list-decimal pl-5 text-sm space-y-1 text-on-surface-variant dark:text-light-muted mb-3">
          {pendingPlan.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
        <button onClick={() => runPlan()} className="px-4 py-1.5 bg-accent-terracotta hover:bg-accent-deep text-white text-[11px] uppercase tracking-wide rounded-lg active:scale-95 transition">Run this plan</button>
      </div>
    </div>
  );
}

function ApprovalModal() {
  const { pendingApproval, respond } = useStore();
  useEffect(() => {
    if (!pendingApproval) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") respond(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pendingApproval, respond]);
  if (!pendingApproval) return null;
  const a = pendingApproval;
  const risk = a.risk === "critical" ? "bg-red-100 text-red-700" : a.risk === "write" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm">
      <div role="dialog" aria-modal="true" aria-label="Approval required"
        className="w-full max-w-md bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-2xl p-6 fadeup">
        <div className="flex items-center gap-2 mb-3">
          <span className="material-symbols-outlined text-red-500">gpp_maybe</span>
          <h4 className="font-headline text-lg font-semibold">Approval required</h4>
        </div>
        <div className="flex items-center gap-2 mb-3 text-sm">
          <span>Tool <b>{a.tool}</b></span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${risk}`}>{a.risk}</span>
        </div>
        <pre className="bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg p-3 text-[12px] font-code overflow-x-auto mb-3">{JSON.stringify(a.args, null, 2)}</pre>
        <div className="text-xs text-on-surface-variant dark:text-light-muted mb-1">policy: {a.reason}</div>
        {a.manager_reason && <div className="text-xs text-on-surface-variant dark:text-light-muted mb-4">security manager: {a.manager_reason}</div>}
        <div className="flex gap-3 mt-4">
          <button onClick={() => respond(true)} className="flex-1 py-2.5 bg-accent-terracotta hover:bg-accent-deep text-white font-medium rounded-lg active:scale-95 transition">Approve</button>
          <button onClick={() => respond(false)} className="flex-1 py-2.5 border border-light-border dark:border-dark-border rounded-lg hover:bg-surface-container-low dark:hover:bg-dark-bg transition">Deny</button>
        </div>
      </div>
    </div>
  );
}

export default function Chat() {
  const { messages } = useStore();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.scrollTo(0, ref.current.scrollHeight); }, [messages]);

  return (
    <>
      <div ref={ref} className="flex-1 overflow-y-auto scrollbar flex flex-col items-center px-gutter">
        <div className="w-full max-w-[760px] py-8 space-y-8">
          {messages.map((m, i) => (
            <Message key={m.id} m={m} index={i} isLast={i === messages.length - 1 && m.role === "assistant"} />
          ))}
          <PlanCard />
        </div>
      </div>
      <ApprovalModal />
    </>
  );
}
