import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore, type Msg, type Ev } from "../lib/store";
import { CodeBlock } from "./CodeBlock";
import { Mermaid } from "./Mermaid";
import Sunburst from "./Sunburst";

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

// A single live checklist for the LEAD's plan — updates in place (✓ done / ● doing /
// ○ pending) instead of printing the whole plan again on every update.
function PlanChecklist({ todos }: { todos?: { text: string; status?: string }[] }) {
  if (!todos?.length) return null;
  return (
    <div className="mb-4 rounded-lg border border-light-border/60 dark:border-dark-border p-3">
      <div className="text-[10px] uppercase tracking-widest text-light-muted mb-2">Plan</div>
      <ul className="space-y-1.5">
        {todos.map((t, i) => {
          const s = t.status || "pending";
          const mark = s === "done" ? "✓" : s === "in_progress" ? "●" : "○";
          const cls = s === "done" ? "text-emerald-600"
            : s === "in_progress" ? "text-accent-terracotta" : "text-light-muted";
          return (
            <li key={i} className="flex items-start gap-2 text-xs">
              <span className={`${cls} ${s === "in_progress" ? "animate-pulse" : ""} mt-px`}>{mark}</span>
              <span className={s === "done" ? "line-through text-light-muted" : "text-on-surface-variant dark:text-light-muted"}>{t.text}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ---- Run flow: group a run's events into Steps, each a collapsible card ------
type Step = { agent: string; label: string; subtask?: string; model?: string;
              tools: Ev[]; notes: Ev[] };

function groupSteps(events: Ev[]): Step[] {
  const steps: Step[] = [];
  let cur: Step | null = null;
  const ensure = (a: string, label?: string) => {
    if (!cur) { cur = { agent: a, label: label || a, tools: [], notes: [] }; steps.push(cur); }
    return cur;
  };
  for (const ev of events) {
    if (ev.type === "assign") {
      cur = { agent: ev.agent, label: ev.label || ev.agent, subtask: ev.subtask,
              model: ev.model, tools: [], notes: [] };
      steps.push(cur);
    } else if (ev.type === "tool") {
      ensure((ev as any).agent || "agent").tools.push(ev);
    } else if (["skill", "memory", "fallback", "retry", "critic", "blocked", "denied", "error"].includes(ev.type)) {
      ensure((ev as any).agent || "agent").notes.push(ev);
    }
  }
  return steps;
}

const WRITE_TOOLS = ["write_file", "edit_file", "apply_patch", "create_file"];
const READ_TOOLS = ["read_file", "list_files", "grep", "glob", "parse_document"];

function stepSummary(s: Step): string {
  const paths = (names: string[]) => s.tools.filter((t) => names.includes(t.name))
    .map((t) => t.args?.path).filter(Boolean);
  const wrote = paths(WRITE_TOOLS);
  const ran = s.tools.filter((t) => t.name === "run_bash").length;
  const searched = s.tools.filter((t) => ["web_search", "web_fetch", "internet_search", "search"].includes(t.name)).length;
  const parts: string[] = [];
  if (wrote.length) parts.push(`wrote ${[...new Set(wrote)].slice(0, 3).join(", ")}${wrote.length > 3 ? "…" : ""}`);
  if (ran) parts.push(`ran ${ran} command${ran > 1 ? "s" : ""}`);
  if (searched) parts.push(`${searched} web search${searched > 1 ? "es" : ""}`);
  if (!parts.length) {
    const read = s.tools.filter((t) => READ_TOOLS.includes(t.name)).length;
    if (read) parts.push(`explored ${read} file${read > 1 ? "s" : ""}`);
  }
  return parts.join(" · ") || s.subtask || "working";
}

// One tool call inside a step. Write/edit calls expand to the full code they wrote
// (syntax-highlighted); everything else stays a one-line arg summary.
function ToolRow({ t }: { t: Ev }) {
  const code = writeCode(t);
  const argStr = code ? (t.args?.path || "")
    : Object.entries(t.args || {}).map(([k, v]) => `${k}=${JSON.stringify(v).slice(0, 32)}`).join(" ");
  const head = (
    <div className="text-[11px] font-code text-on-surface-variant dark:text-light-muted flex items-start gap-1.5">
      <span className="text-accent-terracotta">{t.name}</span>
      <span className="truncate opacity-80">{argStr}</span>
      {code && <span className="ml-auto shrink-0 text-light-muted">{code.split("\n").length} lines</span>}
      {t.result != null && String(t.result).startsWith("exit=") && (
        <span className="ml-auto shrink-0 text-emerald-600 dark:text-emerald-400">{String(t.result).split("\n")[0]}</span>
      )}
    </div>
  );
  if (!code) return head;
  return (
    <details className="group/code">
      <summary className="cursor-pointer list-none">{head}</summary>
      <div className="mt-1"><CodeBlock lang={codeLang(t.args?.path)} code={code} /></div>
    </details>
  );
}

function StepCard({ step, defaultOpen }: { step: Step; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const failed = step.notes.find((n) => ["error", "blocked", "denied"].includes(n.type));
  return (
    <div className={`border rounded-lg overflow-hidden ml-6 ${failed ? "border-red-400/50" : "border-light-border dark:border-dark-border"}`}>
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-surface-container-low dark:hover:bg-dark-bg/40 transition">
        <span className="material-symbols-outlined text-light-muted text-[15px]">{open ? "expand_more" : "chevron_right"}</span>
        <span className="text-[10px] font-code font-semibold px-1.5 py-0.5 rounded bg-emerald-500/12 text-emerald-700 dark:text-emerald-400">{step.label}</span>
        <span className="text-[12px] flex-1 truncate text-on-surface dark:text-dark-text">{stepSummary(step)}</span>
        {step.tools.length > 0 && <span className="text-[10px] font-code text-light-muted">{step.tools.length} tool{step.tools.length > 1 ? "s" : ""}</span>}
      </button>
      {open && (
        <div className="border-t border-light-border/50 dark:border-dark-border px-3 py-2 bg-surface-container-low/60 dark:bg-dark-bg/40 space-y-1">
          {step.tools.map((t, i) => <ToolRow key={i} t={t} />)}
          {step.notes.map((n, i) => {
            const d = describe(n);
            if (!d) return null;
            return <div key={`n${i}`} className="text-[11px] text-light-muted flex items-center gap-1.5">
              <span className={`px-1 py-px rounded text-[8px] font-bold uppercase ${PILL[n.type] || "bg-surface-container"}`}>{d.label}</span>
              <span className="truncate">{d.text}</span></div>;
          })}
        </div>
      )}
    </div>
  );
}

function PhaseLabel({ icon, color, children }: { icon: string; color: string; children: any }) {
  return (
    <div className="flex items-center gap-2 mt-3 mb-1.5">
      <span className={`w-4 h-4 rounded grid place-items-center text-white text-[11px] ${color}`}>
        <span className="material-symbols-outlined text-[12px]">{icon}</span></span>
      <span className="text-[10px] uppercase tracking-widest text-light-muted font-medium">{children}</span>
    </div>
  );
}

// Compact integer label: 18234 -> "18.2k", 2_100_000 -> "2.1M".
function fmtCompact(n?: number): string {
  if (!n && n !== 0) return "";
  if (n < 1000) return `${n}`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}k`.replace(".0k", "k");
  return `${(n / 1_000_000).toFixed(1)}M`;
}

// Whether a run produced enough detail to be worth its own Plan/Steps/Verify card.
function hasRunDetail(events: Ev[], running?: boolean): boolean {
  const steps = groupSteps(events);
  const lastPlan = [...events].reverse().find((e) => e.type === "plan") as any;
  const worthShowing = events.some((e) => MEANINGFUL.includes(e.type)) ||
    events.filter((e) => e.type === "assign").length > 1 || !!running;
  const hasWork = steps.some((s) => s.tools.length || s.notes.length) || !!lastPlan?.todos?.length;
  const hasProgram = events.some((e) => e.type === "program");
  return (hasWork && worthShowing) || hasProgram;
}

// The always-visible run-summary header: a verdict pill + metric columns
// (time · steps · tokens · % cached · cost · tools). Replaces the plain "Run" bar.
function RunSummary({ m, running, steps, critic }: { m: Msg; running?: boolean; steps: number; critic: Ev[] }) {
  const meta = m.meta;
  const tools = m.events.filter((e) => e.type === "tool").length;
  const failed = critic.some((c) => !(c as any).passed);
  const dur = fmtDur(meta?.durationMs);
  const cachedPct = meta?.cachedTokens && meta?.tokens
    ? Math.round((meta.cachedTokens / meta.tokens) * 100) : 0;
  const ctxPct = meta?.contextTokens && meta?.contextBudget
    ? Math.min(100, Math.round((meta.contextTokens / meta.contextBudget) * 100)) : 0;
  // The model that produced this answer: the last agent's model, else the router's pick.
  const assigns = m.events.filter((e) => e.type === "assign" && (e as any).model);
  const routeEv = [...m.events].reverse().find((e) => e.type === "route") as any;
  const modelRaw: string = (assigns.length ? (assigns[assigns.length - 1] as any).model : routeEv?.routed_model) || "";
  const model = modelRaw ? String(modelRaw).split("/").pop() : "";

  type M = { k: string; v: string; accent?: boolean };
  const cols: M[] = [];
  if (dur) cols.push({ k: "time", v: dur });
  if (steps > 0) cols.push({ k: "steps", v: `${steps}` });
  if (meta?.tokens) cols.push({ k: "tokens", v: fmtCompact(meta.tokens) });
  if (ctxPct > 0) cols.push({ k: "context", v: `${ctxPct}%`, accent: ctxPct >= 80 });
  if (cachedPct > 0) cols.push({ k: "cached", v: `${cachedPct}%`, accent: true });
  if (meta?.cost) cols.push({ k: "cost", v: `$${meta.cost.toFixed(3)}` });
  if (tools > 0) cols.push({ k: "tools", v: `${tools}` });

  const verdict = running
    ? { label: "Working", cls: "text-accent-deep bg-accent-terracotta/12", dot: "bg-accent-terracotta animate-pulse", icon: "" }
    : failed
    ? { label: "Needs review", cls: "text-amber-700 dark:text-amber-400 bg-amber-500/12", dot: "", icon: "warning" }
    : { label: "Done", cls: "text-emerald-700 dark:text-emerald-400 bg-emerald-500/12", dot: "", icon: "check" };

  return (
    <div className="flex items-center gap-x-4 gap-y-2 flex-wrap px-3.5 py-2.5 border-b border-light-border/50 dark:border-dark-border bg-surface-container-low/60 dark:bg-dark-bg/40">
      <span className={`inline-flex items-center gap-1.5 text-[11.5px] font-semibold px-2.5 py-1 rounded-full ${verdict.cls}`}>
        {verdict.dot ? <span className={`w-1.5 h-1.5 rounded-full ${verdict.dot}`} />
          : <span className="material-symbols-outlined text-[13px]">{verdict.icon}</span>}
        {verdict.label}
      </span>
      {cols.length > 0 && (
        <div className="flex items-center">
          {cols.map((c, i) => (
            <div key={c.k} className={`flex flex-col px-3 ${i > 0 ? "border-l border-light-border dark:border-dark-border" : ""}`}>
              <span className={`text-[12.5px] font-semibold leading-tight tabular-nums ${c.accent ? "text-accent-deep dark:text-accent-terracotta" : "text-on-surface dark:text-dark-text"}`}>{c.v}</span>
              <span className="text-[9px] uppercase tracking-[0.08em] text-light-muted">{c.k}</span>
            </div>
          ))}
        </div>
      )}
      {model && (
        <span className="text-[10px] text-light-muted font-code truncate max-w-[180px] flex items-center gap-1 ml-auto" title={modelRaw}>
          <span className="material-symbols-outlined text-[13px]">memory</span>{model}
        </span>
      )}
    </div>
  );
}

// Sequential task-runner: a live checklist + progress bar built from the latest `program`
// event. Shows which of a numbered/bulleted list is done / running / pending, and how far along.
function ProgramProgress({ events }: { events: Ev[] }) {
  const prog = [...events].reverse().find((e) => e.type === "program") as any;
  if (!prog?.tasks?.length) return null;
  const glyph: Record<string, string> = { done: "✓", error: "⚠", skipped: "⏭", in_progress: "●", pending: "○" };
  const tone: Record<string, string> = {
    done: "text-emerald-600", error: "text-amber-600", skipped: "text-light-muted",
    in_progress: "text-accent-terracotta", pending: "text-light-muted",
  };
  const pct = prog.total ? Math.round((prog.done / prog.total) * 100) : 0;
  return (
    <div className="mb-3">
      <PhaseLabel icon="list_alt" color="bg-accent-terracotta">Tasks · {prog.done}/{prog.total}</PhaseLabel>
      <div className="ml-6">
        <div className="h-1.5 rounded-full bg-surface-container-high dark:bg-dark-border overflow-hidden mb-2">
          <div className="h-full rounded-full bg-accent-terracotta transition-all duration-500" style={{ width: `${pct}%` }} />
        </div>
        <div className="space-y-1">
          {prog.tasks.map((t: any, i: number) => (
            <div key={i} className="flex items-start gap-2 text-[12px]">
              <span className={`${tone[t.status] || "text-light-muted"} ${t.status === "in_progress" ? "animate-pulse" : ""} w-4 shrink-0 text-center`}>{glyph[t.status] || "○"}</span>
              <span className={t.status === "in_progress" ? "text-on-surface dark:text-dark-text font-medium"
                : t.status === "pending" ? "text-light-muted" : "text-on-surface-variant dark:text-light-muted"}>
                {i + 1}. {t.text}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Activity({ m, running }: { m: Msg; running?: boolean }) {
  const events = m.events;
  const lastPlan = [...events].reverse().find((e) => e.type === "plan") as any;
  const steps = groupSteps(events);
  const critic = events.filter((e) => e.type === "critic");
  if (!hasRunDetail(events, running)) return null;
  return (
    <div className="mt-3 border border-light-border dark:border-dark-border rounded-xl overflow-hidden">
      <RunSummary m={m} running={running} steps={steps.length} critic={critic} />
      <AgentStatus events={events} running={running} />
      <div className="px-4 pb-4 pt-1">
        <ProgramProgress events={events} />
        {lastPlan?.todos?.length > 0 && (<><PhaseLabel icon="checklist" color="bg-accent-terracotta">Plan</PhaseLabel><PlanChecklist todos={lastPlan.todos} /></>)}
        {steps.length > 0 && (
          <><PhaseLabel icon="settings" color="bg-accent-terracotta">Steps</PhaseLabel>
          <div className="space-y-2">
            {steps.map((s, i) => <StepCard key={i} step={s} defaultOpen={!!running && i === steps.length - 1} />)}
          </div></>
        )}
        {critic.length > 0 && (
          <><PhaseLabel icon="verified" color="bg-emerald-600">Verify</PhaseLabel>
          {critic.map((c, i) => (
            <div key={i} className="ml-6 text-[12px] flex items-center gap-2">
              <span className={c.passed ? "text-emerald-600" : "text-amber-600"}>{c.passed ? "✓" : "⚠"}</span>
              <span className="text-on-surface-variant dark:text-light-muted">{c.summary || (c.passed ? "checks passed" : "issues found")}</span>
            </div>
          ))}</>
        )}
      </div>
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

// The model's live chain-of-thought (reasoning_content). Auto-expanded and scrolling
// while the model is still thinking; collapses to a click-to-expand summary once done.
function ThinkingBlock({ text, live }: { text: string; live: boolean }) {
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (live && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [text, live]);
  const body = (
    <div ref={bodyRef} className="max-h-52 overflow-y-auto font-code text-[12px] leading-5 text-on-surface-variant dark:text-light-muted whitespace-pre-wrap">
      {text}{live && <span className="caret" />}
    </div>
  );
  const label = (
    <span className="flex items-center gap-1.5 text-[9px] uppercase tracking-widest text-light-muted font-bold">
      {live && <span className="w-1.5 h-1.5 rounded-full bg-light-muted animate-pulse" />}
      {live ? "thinking…" : "thought process"}
    </span>
  );
  const box = "mb-2 rounded-xl border border-light-border dark:border-dark-border bg-surface-container-low dark:bg-dark-bg/40 px-3 py-2";
  if (live) return <div className={box}>{<div className="mb-1">{label}</div>}{body}</div>;
  return (
    <details className={box}>
      <summary className="cursor-pointer list-none select-none">{label}</summary>
      <div className="mt-1">{body}</div>
    </details>
  );
}

// The code content a write/edit tool call carries (write_file.content / edit_file.new_string).
function writeCode(ev?: Ev): string | null {
  if (!ev || !WRITE_TOOLS.includes(ev.name)) return null;
  const c = ev.args?.content ?? ev.args?.new_string;
  return typeof c === "string" && c.length ? c : null;
}
function latestWrite(events: Ev[]): Ev | undefined {
  for (let i = events.length - 1; i >= 0; i--)
    if (events[i].type === "tool" && writeCode(events[i])) return events[i];
  return undefined;
}
function codeLang(path?: string): string | undefined {
  const ext = (path || "").split(".").pop()?.toLowerCase();
  const map: Record<string, string> = { js: "javascript", ts: "typescript", jsx: "jsx", tsx: "tsx",
    py: "python", html: "html", css: "css", json: "json", md: "markdown", sh: "bash", yaml: "yaml", yml: "yaml" };
  return ext ? map[ext] : undefined;
}

// "Watch the code being written" — reveals the file the run is currently writing. The
// content is the real tool-call payload (tool-calling requests are non-streamed to keep
// weak build models reliable), revealed progressively client-side so it reads live.
function LiveCode({ ev }: { ev?: Ev }) {
  const code = writeCode(ev) || "";
  const path = ev?.args?.path || "file";
  const [shown, setShown] = useState(0);
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setShown(0);
    if (!code) return;
    const step = Math.max(8, Math.floor(code.length / 100));
    const id = setInterval(() => setShown((n) => {
      const next = n + step;
      if (next >= code.length) clearInterval(id);
      return Math.min(next, code.length);
    }), 24);
    return () => clearInterval(id);
  }, [code]);
  useEffect(() => { if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight; }, [shown]);
  if (!code) return null;
  return (
    <div className="mt-2 rounded-xl border border-light-border dark:border-dark-border bg-surface-container-low dark:bg-dark-bg/60 overflow-hidden">
      <div className="flex items-center gap-1.5 px-3 py-1.5 text-[9px] uppercase tracking-widest text-accent-terracotta font-bold border-b border-light-border/50 dark:border-dark-border">
        <span className="w-1.5 h-1.5 rounded-full bg-accent-terracotta animate-pulse" /> writing <span className="font-code normal-case tracking-normal opacity-80">{path}</span>
      </div>
      <div ref={bodyRef} className="max-h-64 overflow-y-auto px-3 py-2">
        <pre className="font-code text-[12px] leading-5 text-on-surface-variant dark:text-light-muted whitespace-pre-wrap">{code.slice(0, shown)}<span className="caret" /></pre>
      </div>
    </div>
  );
}

function Message({ m, index, isLast }: { m: Msg; index: number; isLast?: boolean }) {
  if (m.role === "user") return <UserMessage m={m} index={index} />;
  return (
    <div className="fadeup group">
      {m.thinking ? <ThinkingBlock text={m.thinking} live={!!m.pending} /> : null}
      {m.content ? (
        <div className="prose-msg text-on-surface dark:text-dark-text">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>{m.content}</ReactMarkdown>
          {m.pending && <span className="caret" />}
        </div>
      ) : m.pending && !m.live ? (
        <div className="flex items-center gap-2 text-light-muted text-sm">
          <Sunburst size={17} className="nikki-spin" /> Thinking…
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
      {m.pending ? <LiveCode ev={latestWrite(m.events)} /> : null}
      {m.events.length > 0 && <Activity m={m} running={m.pending} />}
      {m.content && !m.pending && <ResponseFooter m={m} last={isLast} hideStats={hasRunDetail(m.events, false)} />}
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
function ResponseFooter({ m, last, hideStats }: { m: Msg; last?: boolean; hideStats?: boolean }) {
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
  // Provider-reported prompt-cache reads (cache-hit input is ~50-98% cheaper) — shown
  // as a share of all tokens so the savings from a stable prompt prefix are visible.
  if (meta?.cachedTokens && meta?.tokens)
    stats.push(`${Math.round((meta.cachedTokens / meta.tokens) * 100)}% cached`);
  if (meta?.cost) stats.push(`$${meta.cost.toFixed(4)}`);
  if (tools.length) stats.push(`${tools.length} tool${tools.length > 1 ? "s" : ""}`);

  return (
    <div className="mt-2.5 space-y-1.5">
      {((!hideStats && stats.length > 0) || fileChanges.length > 0) && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-light-muted">
          {!hideStats && stats.length > 0 && (
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
