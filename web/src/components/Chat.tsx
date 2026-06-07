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

const SUGGESTIONS = [
  "Write a Python function to check if a number is prime",
  "Explain how async/await works in JavaScript",
  "Build a simple landing page in HTML",
  "Summarize the pros and cons of microservices",
];

const PILL: Record<string, string> = {
  route: "bg-blue-100 text-blue-700",
  plan: "bg-amber-100 text-amber-700",
  assign: "bg-emerald-100 text-emerald-700",
  thought: "bg-surface-container-highest text-on-surface-variant",
  tool: "bg-accent-terracotta/10 text-accent-terracotta",
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
    case "manager_review": return { label: "Security", text: <>{ev.approved ? "approved" : "denied"} — {ev.reason}</> };
    case "critic": return { label: "QA", text: <><b>{ev.passed ? "pass" : "fail"}</b> — {ev.summary}</> };
    case "memory": return { label: "Memory", text: `recalled ${ev.items?.length} note(s) from past chats` };
    case "skill": return { label: "Skill", text: <>applied skill{ev.skills?.length > 1 ? "s" : ""}: <b>{(ev.skills || []).join(", ")}</b></> };
    case "blocked": case "denied": return { label: ev.type, text: `${ev.name}: ${ev.reason}` };
    case "error": case "limit": case "stopping": return { label: "System", text: ev.text || "stopping…" };
    default: return null;
  }
}

const MEANINGFUL = ["plan", "tool", "critic", "manager_review", "memory", "skill", "blocked", "denied"];

const FIXABLE = ["error", "blocked", "denied", "limit"];

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
    <div className="mt-3 border border-light-border dark:border-dark-border rounded-lg overflow-hidden">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between px-3 py-1.5 hover:bg-surface-container-low dark:hover:bg-dark-bg/50 transition">
        <div className="flex items-center gap-2 text-light-muted">
          <span className={`w-1.5 h-1.5 rounded-full ${running ? "bg-accent-terracotta animate-pulse" : "bg-light-muted"}`} />
          <span className="text-[11px] uppercase tracking-wide">Agent activity · {steps.length} steps</span>
        </div>
        <span className="material-symbols-outlined text-light-muted text-[16px]">{open ? "expand_less" : "expand_more"}</span>
      </button>
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
      <div className="flex justify-end fadeup">
        <div className="w-[85%] bg-white dark:bg-dark-surface border border-accent-terracotta/40 rounded-2xl p-3">
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
    <div className="flex justify-end fadeup group">
      <div className="flex items-start gap-1.5 max-w-[85%]">
        {!running && (
          <button onClick={() => { setDraft(m.content); setEditing(true); }} title="Edit & branch"
            className="material-symbols-outlined text-[16px] text-light-muted hover:text-on-surface dark:hover:text-dark-text opacity-0 group-hover:opacity-100 mt-3">edit</button>
        )}
        <div className="bg-surface-container-high/70 dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl px-5 py-3 shadow-sm">
          <p className="text-[15px] whitespace-pre-wrap">{m.content}</p>
        </div>
      </div>
    </div>
  );
}

function Message({ m, index, isLast }: { m: Msg; index: number; isLast?: boolean }) {
  if (m.role === "user") return <UserMessage m={m} index={index} />;
  return (
    <div className="fadeup group">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-6 h-6 rounded bg-accent-terracotta flex items-center justify-center text-white text-[10px] font-bold">A</div>
        <span className="text-[11px] uppercase tracking-widest font-bold">Assistant</span>
      </div>
      <div className="pl-8">
        {m.content ? (
          <div className="prose-msg text-on-surface dark:text-dark-text">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>{m.content}</ReactMarkdown>
            {m.pending && <span className="caret" />}
          </div>
        ) : m.pending && !m.live ? (
          <span className="text-light-muted text-sm">working…</span>
        ) : null}
        {m.live ? (
          <div className="mt-2 rounded-lg border border-light-border dark:border-dark-border bg-surface-container-low dark:bg-dark-bg/60 px-3 py-2">
            <div className="flex items-center gap-1.5 mb-1 text-[9px] uppercase tracking-widest text-accent-terracotta font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-terracotta animate-pulse" /> streaming
            </div>
            <div className="font-code text-[12px] leading-5 text-on-surface-variant dark:text-light-muted whitespace-pre-wrap">{m.live}<span className="caret" /></div>
          </div>
        ) : null}
        {m.events.length > 0 && <Activity events={m.events} running={m.pending} />}
        {m.content && !m.pending && <MessageActions content={m.content} last={isLast} />}
      {/* actions row uses group-hover from the wrapper above */}
      </div>
    </div>
  );
}

function MessageActions({ content, last }: { content: string; last?: boolean }) {
  const { regenerate, running, sendFeedback } = useStore();
  const [copied, setCopied] = useState(false);
  const [fb, setFb] = useState("");
  const copy = () => { navigator.clipboard?.writeText(content); setCopied(true); setTimeout(() => setCopied(false), 1200); };
  const btn = "p-1.5 rounded-md text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg";
  return (
    <div className="flex items-center gap-1 mt-2 opacity-0 group-hover:opacity-60 hover:!opacity-100 focus-within:opacity-100 transition">
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
  );
}

function PlanCard() {
  const { pendingPlan, runPlan, running } = useStore();
  if (!pendingPlan || running) return null;
  return (
    <div className="pl-8 fadeup">
      <div className="border border-accent-terracotta/40 bg-accent-terracotta/5 rounded-xl p-4 max-w-[760px]">
        <p className="text-[11px] uppercase tracking-widest font-bold text-accent-terracotta mb-2">▶ Plan ready</p>
        <ol className="list-decimal pl-5 text-sm space-y-1 text-on-surface-variant dark:text-light-muted mb-3">
          {pendingPlan.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
        <button onClick={() => runPlan()} className="px-4 py-1.5 bg-accent-terracotta text-white text-[11px] uppercase tracking-wide rounded-lg hover:brightness-110 active:scale-95 transition">Run this plan</button>
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
          <h4 className="font-display text-lg font-semibold">Approval required</h4>
        </div>
        <div className="flex items-center gap-2 mb-3 text-sm">
          <span>Tool <b>{a.tool}</b></span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${risk}`}>{a.risk}</span>
        </div>
        <pre className="bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg p-3 text-[12px] font-code overflow-x-auto mb-3">{JSON.stringify(a.args, null, 2)}</pre>
        <div className="text-xs text-on-surface-variant dark:text-light-muted mb-1">policy: {a.reason}</div>
        {a.manager_reason && <div className="text-xs text-on-surface-variant dark:text-light-muted mb-4">security manager: {a.manager_reason}</div>}
        <div className="flex gap-3 mt-4">
          <button onClick={() => respond(true)} className="flex-1 py-2.5 bg-accent-terracotta text-white font-medium rounded-lg hover:brightness-110 active:scale-95 transition">Approve</button>
          <button onClick={() => respond(false)} className="flex-1 py-2.5 border border-light-border dark:border-dark-border rounded-lg hover:bg-surface-container-low dark:hover:bg-dark-bg transition">Deny</button>
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  const { submit } = useStore();
  return (
    <div className="text-center mt-[16vh]">
      <h2 className="font-display text-3xl font-semibold mb-3">What should we build?</h2>
      <p className="text-light-muted mb-6">Ask anything — coding or general. A complex goal is split across specialist agents automatically.</p>
      <div className="flex flex-wrap gap-2 justify-center max-w-[640px] mx-auto">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => submit(s)}
            className="text-left text-sm px-3.5 py-2 rounded-xl border border-light-border dark:border-dark-border bg-white dark:bg-dark-surface hover:border-accent-terracotta/40 hover:bg-surface-container-low dark:hover:bg-dark-bg transition text-on-surface-variant dark:text-light-muted">
            {s}
          </button>
        ))}
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
        <div className="w-full max-w-[760px] py-10 space-y-10">
          {messages.length === 0 && <EmptyState />}
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
