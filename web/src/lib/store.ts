import { create } from "zustand";
import { api, wsUrl } from "./api";
import { downloadBlob } from "./util";

export type Ev = any;
export type FileChange = { path: string; status: string; added: number; removed: number };
export type RunMeta = { durationMs?: number; tokens?: number; cost?: number; iterations?: number; cachedTokens?: number; files?: FileChange[] };
export type Msg = { id: string; role: "user" | "assistant"; content: string; events: Ev[]; pending?: boolean; live?: string; local?: boolean; meta?: RunMeta };

// Stable client id for a message (used as the React key so edit/branch can't
// attach stale component state to the wrong message).
let _mid = 0;
const newMid = () => `m${Date.now()}_${_mid++}`;
let _tid = 0;
let _runStart = 0;   // wall-clock start of the current run (for the response summary)
export type Attachment = { path: string; name: string };
export type Toast = { id: number; text: string; kind: "info" | "error" | "success" };

type State = {
  connected: boolean;
  sessions: any[];
  currentId: string | null;
  messages: Msg[];
  running: boolean;
  cost: number;
  pendingApproval: Ev | null;
  tiers: Record<string, any>;
  catalog: any[];
  resolved: Record<string, string>;
  strategy: string;
  agents: any[];
  skills: any[];
  commands: { name: string; description: string; argument_hint: string }[];
  draft: string;
  projects: any[];
  activeProject: string;
  files: any[];
  checkpoints: any[];
  jobs: any[];
  trace: any | null;
  facts: any[];
  rules: any[];
  spend: { spent_today: number; cap: number | null; remaining: number | null } | null;
  selected: { path: string; ext?: string; content?: string; binary?: boolean } | null;
  maxUsd: number;
  maxIter: number;
  mode: "auto" | "careful" | "trusted";
  planFirst: boolean;
  pendingPlan: string[] | null;
  review: boolean;
  parallel: boolean;
  stream: boolean;
  acceptance: string;
  effort: "low" | "default" | "high";
  modelOverride: string;
  attachments: Attachment[];
  toasts: Toast[];

  init: () => Promise<void>;
  selectSession: (id: string) => Promise<void>;
  newSession: () => Promise<void>;
  renameSession: (id: string, title: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  toggleStar: (id: string) => Promise<void>;
  sendFeedback: (value: string) => void;
  setTier: (tier: string, model: string) => Promise<void>;
  scoutModels: () => Promise<void>;
  loadSkills: () => Promise<void>;
  loadCommands: () => Promise<void>;
  setDraft: (v: string) => void;
  loadProjects: () => Promise<void>;
  createProject: (name: string) => Promise<void>;
  setActiveProject: (pid: string) => Promise<void>;
  submit: (text: string) => void;
  send: (text: string) => void;
  runPlan: () => void;
  regenerate: () => void;
  editMessage: (index: number, newText: string) => Promise<void>;
  addAttachment: (file: File) => Promise<void>;
  removeAttachment: (path: string) => void;
  setPlanFirst: (v: boolean) => void;
  setReview: (v: boolean) => void;
  setParallel: (v: boolean) => void;
  setStream: (v: boolean) => void;
  setAcceptance: (v: string) => void;
  setEffort: (v: "low" | "default" | "high") => void;
  setModelOverride: (v: string) => void;
  stop: () => void;
  respond: (allowed: boolean) => void;
  loadFiles: () => Promise<void>;
  openFile: (path: string) => Promise<void>;
  loadCheckpoints: () => Promise<void>;
  restore: (id: string) => Promise<void>;
  loadJobs: () => Promise<void>;
  enqueueJob: (text: string) => Promise<void>;
  loadTrace: () => Promise<void>;
  loadFacts: () => Promise<void>;
  forgetFact: (id: string) => Promise<void>;
  addFact: (text: string, key: string) => Promise<void>;
  loadRules: () => Promise<void>;
  approveRule: (id: string) => Promise<void>;
  deleteRule: (id: string) => Promise<void>;
  addRule: (text: string) => Promise<void>;
  loadSpend: () => Promise<void>;
  setLimit: (k: "maxUsd" | "maxIter", v: number) => void;
  setMode: (m: "auto" | "careful" | "trusted") => void;
  exportChat: () => void;
  theme: "light" | "dark";
  toggleTheme: () => void;
  pushToast: (text: string, kind?: Toast["kind"]) => void;
  dismissToast: (id: number) => void;
};

// Single source of truth for the theme (was duplicated + desyncing across Sidebar
// and SettingsModal). Persisted so it survives a reload.
function applyTheme(theme: "light" | "dark") {
  const el = document.documentElement;
  el.classList.toggle("dark", theme === "dark");
  el.classList.toggle("light", theme === "light");
  try { localStorage.setItem("agent_theme", theme); } catch { /* ignore */ }
}

const _initialTheme: "light" | "dark" =
  (typeof localStorage !== "undefined" && localStorage.getItem("agent_theme") === "dark") ? "dark" : "light";

let socket: WebSocket | null = null;
// The session the live socket belongs to, so events that arrive after the user
// switches chats can't mutate the wrong session's messages.
let socketSession: string | null = null;

function closeSocket() {
  if (socket) {
    try { socket.onclose = null; socket.close(); } catch { /* ignore */ }
  }
  socket = null;
  socketSession = null;
}

export const useStore = create<State>((set, get) => ({
  connected: false,
  sessions: [],
  currentId: null,
  messages: [],
  running: false,
  cost: 0,
  pendingApproval: null,
  tiers: {},
  catalog: [],
  resolved: {},
  strategy: "fixed",
  agents: [],
  skills: [],
  projects: [],
  activeProject: "",
  files: [],
  checkpoints: [],
  jobs: [],
  trace: null,
  facts: [],
  rules: [],
  spend: null,
  selected: null,
  maxUsd: 0.5,
  maxIter: 20,
  mode: "auto",
  planFirst: false,
  pendingPlan: null,
  review: false,
  parallel: false,
  stream: true,
  acceptance: "",
  effort: "default",
  modelOverride: "",
  attachments: [],
  commands: [],
  draft: "",
  toasts: [],

  async init() {
    applyTheme(get().theme);   // restore the persisted theme on load
    try {
      const [m, ag, sk, cmds, sessions, projects] = await Promise.all([api.models(), api.agents(), api.skills(), api.commands(), api.listSessions(), api.listProjects()]);
      set({ tiers: m.tiers, catalog: m.catalog, resolved: m.resolved || {},
            strategy: m.strategy || "fixed", agents: ag, skills: sk || [], commands: cmds || [], sessions, projects, connected: true });
      let list = sessions;
      if (!list.length) {
        const s = await api.createSession("New chat");
        list = [s];
        set({ sessions: list });
      }
      await get().selectSession(list[0].id);
      get().loadSpend();
    } catch (e) {
      set({ connected: false });
    }
  },

  async selectSession(id) {
    // Tear down any live run before switching, so its socket can't keep mutating
    // the newly-loaded session's messages.
    closeSocket();
    set({ running: false, pendingApproval: null, pendingPlan: null });
    try {
      const msgs = await api.messages(id);
      set({
        currentId: id,
        messages: msgs.map((m: any) => ({ id: newMid(), role: m.role, content: m.content, events: [] })),
        selected: null,
      });
      await get().loadFiles();
      await get().loadCheckpoints();
      // Reattach: if a run for this session is still waiting on a human approval (e.g.
      // the browser was reloaded mid-run), surface it so it can be answered now. The
      // backend resolves it against the live waiting run regardless of which client answers.
      try {
        const ar = await api.activeRun(id);
        const p = (ar?.pending || [])[0];
        if (p && get().currentId === id) {
          let args: any = {};
          try { args = JSON.parse(p.args || "{}"); } catch { /* keep {} */ }
          set({ pendingApproval: { id: p.id, tool: p.tool, risk: p.risk,
                                   reason: p.reason, manager_reason: p.manager_reason, args } });
        }
      } catch { /* no active-run info — fine */ }
    } catch (e) {
      reportError(get, e);
    }
  },

  async newSession() {
    const s = await api.createSession("New chat", get().activeProject || "");
    set({ sessions: [s, ...get().sessions] });
    await get().selectSession(s.id);
  },

  async loadSkills() {
    set({ skills: (await api.skills()) || [] });
  },

  async loadCommands() {
    set({ commands: (await api.commands()) || [] });
  },

  setDraft(v) { set({ draft: v }); },

  async loadProjects() {
    set({ projects: await api.listProjects() });
  },

  async createProject(name) {
    const p = await api.createProject(name);
    set({ projects: [p, ...get().projects] });
    await get().setActiveProject(p.id);
  },

  async setActiveProject(pid) {
    set({ activeProject: pid });
    const list = await api.listSessions(pid || undefined);
    set({ sessions: list });
    if (list.length) await get().selectSession(list[0].id);
    else await get().newSession();
  },

  async renameSession(id, title) {
    await api.renameSession(id, title);
    set({ sessions: get().sessions.map((s) => (s.id === id ? { ...s, title } : s)) });
  },

  async deleteSession(id) {
    await api.deleteSession(id);
    const rest = get().sessions.filter((s) => s.id !== id);
    set({ sessions: rest });
    if (get().currentId === id) {
      if (rest.length) await get().selectSession(rest[0].id);
      else await get().newSession();
    }
  },

  async toggleStar(id) {
    const s = await api.star(id);
    const sessions = get().sessions.map((x) => (x.id === id ? { ...x, starred: s.starred } : x));
    sessions.sort((a, b) => (a.starred ? 0 : 1) - (b.starred ? 0 : 1));
    set({ sessions });
  },

  sendFeedback(value) {
    const id = get().currentId;
    if (id) api.feedback(id, value);
  },

  async setTier(tier, model) {
    await api.setTier(tier, model);
    set({ tiers: { ...get().tiers, [tier]: { ...get().tiers[tier], model } } });
  },

  async scoutModels() {
    const r = await api.scout();
    const props = r.proposal || [];
    if (!props.length) {
      alert("Model scout found no new models (needs a provider key + web access).");
      return;
    }
    const list = props.map((p: any) => `• ${p.id}${p.free ? " (free)" : ""}`).join("\n");
    if (confirm(`Model scout proposes ${props.length} model(s):\n\n${list}\n\nAdd them to the catalog?`)) {
      const ap = await api.applyCatalog(props);
      set({ catalog: ap.catalog });
      const m = await api.models();
      set({ resolved: m.resolved || {} });
      alert("Added. The cost-first selector will use the cheapest available ones automatically.");
    }
  },

  submit(text) {
    const t = text.trim();
    if (!t) return;
    if (t.startsWith("/")) {
      const name = t.slice(1).split(/\s+/)[0].toLowerCase();
      // Built-in client commands run locally; user-authored ones (from config/commands)
      // are sent as a run so the server expands the template. Anything else falls through
      // to handleSlash, which shows the "unknown command" help.
      if (CLIENT_COMMANDS.includes(name)) return handleSlash(set, get, t);
      if (get().commands.some((c) => c.name === name)) return get().send(t);
      return handleSlash(set, get, t);
    }
    get().send(t);
  },

  send(text) {
    const atts = get().attachments;
    const acc = get().acceptance.trim();
    // review is omitted unless the user force-enables it -> backend "auto" mode runs
    // QA automatically on substantive tasks (coding/writing/data + all complex tasks).
    startRun(set, get, {
      text, plan_first: get().planFirst, ...(get().review ? { review: true } : {}),
      parallel: get().parallel, stream: get().stream, effort: get().effort,
      ...(get().modelOverride ? { model_override: get().modelOverride } : {}),
      ...(acc ? { acceptance: acc } : {}),
      attachments: atts.map((a) => a.path),
    }, atts.length ? `${text}\n\n📎 ${atts.map((a) => a.name).join(", ")}` : text);
    set({ attachments: [] });
  },

  runPlan() {
    const subs = get().pendingPlan;
    if (!subs) return;
    startRun(set, get, {
      text: "Run the approved plan", subtasks: subs, ...(get().review ? { review: true } : {}),
      parallel: get().parallel, stream: get().stream, effort: get().effort,
      ...(get().modelOverride ? { model_override: get().modelOverride } : {}),
    }, "▶ Run the approved plan");
  },

  regenerate() {
    if (get().running) return;
    const msgs = get().messages;
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === "user") { get().send(msgs[i].content); return; }
    }
  },

  async editMessage(index, newText) {
    const id = get().currentId;
    if (!id || get().running) return;
    const msgs = get().messages;
    // Keep only DB messages (non-local) that come before the edited message.
    const keep = msgs.slice(0, index).filter((m) => !m.local).length;
    await api.truncate(id, keep);
    set({ messages: msgs.slice(0, index) });   // branch: drop edited msg + everything after
    get().send(newText);
  },

  async addAttachment(file) {
    const id = get().currentId;
    if (!id) return;
    try {
      const r = await api.upload(id, file);
      set({ attachments: [...get().attachments, { path: r.path, name: r.name }] });
    } catch {
      alert("Upload failed.");
    }
  },

  removeAttachment(path) {
    set({ attachments: get().attachments.filter((a) => a.path !== path) });
  },

  setPlanFirst(v) {
    set({ planFirst: v });
  },

  setReview(v) {
    set({ review: v });
  },

  setParallel(v) {
    set({ parallel: v });
  },

  setStream(v) {
    set({ stream: v });
  },

  setEffort(v) {
    set({ effort: v });
  },

  setModelOverride(v) {
    set({ modelOverride: v });
  },

  setAcceptance(v) {
    set({ acceptance: v });
  },

  stop() {
    socket?.send(JSON.stringify({ type: "stop" }));
  },

  respond(allowed) {
    const a = get().pendingApproval;
    if (a) {
      // Live socket if we have one; otherwise resolve over REST — the backend routes
      // either to the same waiting run (works after a reload / from another tab).
      if (socket && get().running) {
        socket.send(JSON.stringify({ type: "approval_response", id: a.id, allowed }));
      } else {
        api.resolveApproval(a.id, allowed).catch(() => { /* best-effort */ });
      }
    }
    set({ pendingApproval: null });
  },

  async loadFiles() {
    const id = get().currentId;
    if (!id) return;
    try {
      const r = await api.files(id);
      set({ files: r.files || [] });
    } catch (e) { reportError(get, e); }
  },

  async openFile(path) {
    const id = get().currentId;
    if (!id) return;
    try {
      const r = await api.readFile(id, path);
      set({ selected: r });
    } catch (e) { reportError(get, e); }
  },

  async loadCheckpoints() {
    const id = get().currentId;
    if (!id) return;
    try {
      set({ checkpoints: await api.checkpoints(id) });
    } catch (e) { reportError(get, e); }
  },

  async loadTrace() {
    const id = get().currentId;
    if (!id) return;
    try {
      set({ trace: await api.traces(id) });
    } catch (e) { reportError(get, e); }
  },

  async restore(cid) {
    const id = get().currentId;
    if (!id) return;
    try {
      await api.restore(id, cid);
      await get().loadFiles();
      appendInfo(set, get, "Workspace restored to an earlier checkpoint.");
    } catch (e) { reportError(get, e); }
  },

  async loadJobs() {
    const id = get().currentId;
    if (!id) return;
    try {
      set({ jobs: await api.jobs(id) });
    } catch (e) { reportError(get, e); }
  },

  async enqueueJob(text) {
    const id = get().currentId;
    if (!id || !text.trim()) return;
    try {
      await api.enqueue(id, text.trim());
      await get().loadJobs();
    } catch (e) { reportError(get, e); }
  },

  async loadFacts() {
    try {
      set({ facts: (await api.memory()) || [] });
    } catch (e) { reportError(get, e); }
  },

  async forgetFact(fid) {
    try {
      const r = await api.forgetFact(fid);
      set({ facts: r.facts || [] });
    } catch (e) { reportError(get, e); }
  },

  async addFact(text, key) {
    if (!text.trim() || !key.trim()) return;
    try {
      const r = await api.addFact(text.trim(), key.trim());
      set({ facts: r.facts || [] });
    } catch (e) { reportError(get, e); }
  },

  async loadRules() {
    try {
      set({ rules: (await api.rules()) || [] });
    } catch (e) { reportError(get, e); }
  },

  async approveRule(id) {
    try {
      const r = await api.approveRule(id);
      set({ rules: r.rules || [] });
    } catch (e) { reportError(get, e); }
  },

  async deleteRule(id) {
    try {
      const r = await api.deleteRule(id);
      set({ rules: r.rules || [] });
    } catch (e) { reportError(get, e); }
  },

  async addRule(text) {
    if (!text.trim()) return;
    try {
      const r = await api.addRule(text.trim());
      set({ rules: r.rules || [] });
    } catch (e) { reportError(get, e); }
  },

  async loadSpend() {
    try {
      set({ spend: await api.spend() });
    } catch (e) { reportError(get, e); }
  },

  setLimit(k, v) {
    set({ [k]: v } as any);
  },

  setMode(m) {
    set({ mode: m });
  },

  theme: _initialTheme,

  toggleTheme() {
    const next = get().theme === "dark" ? "light" : "dark";
    applyTheme(next);
    set({ theme: next });
  },

  pushToast(text, kind = "info") {
    const id = ++_tid;
    set({ toasts: [...get().toasts, { id, text, kind }] });
    setTimeout(() => useStore.getState().dismissToast(id), 4500);
  },

  dismissToast(id) {
    set({ toasts: get().toasts.filter((t) => t.id !== id) });
  },

  exportChat() {
    const { messages, sessions, currentId } = get();
    const title = sessions.find((s) => s.id === currentId)?.title || "chat";
    const md = `# ${title}\n\n` + messages
      .map((m) => `## ${m.role === "user" ? "You" : "Agent Team"}\n\n${m.content}`)
      .join("\n\n");
    downloadBlob(`${title.replace(/[^\w.-]+/g, "_")}.md`, md, "text/markdown");
  },
}));

// Commands handled entirely in the browser (never sent to the server as a run).
const CLIENT_COMMANDS = ["help", "new", "export", "model", "mode"];

const HELP = `**Slash commands**
- \`/new\` — start a new chat
- \`/export\` — download this chat as markdown
- \`/model <tier> <model-id>\` — swap a tier's model (e.g. \`/model tier3 gpt-5.5\`)
- \`/mode auto|careful|trusted\` — set the approval mode
- \`/help\` — show this help

Type \`/\` in the composer to see your own command templates (from \`config/commands\`).`;

// A short chat title from the first message — mirrors server db._derive_title so the
// optimistic UI label matches what the backend persists.
function deriveTitle(text: string): string {
  const t = (text || "").split("\n")[0].replace(/\s+/g, " ").trim();
  if (!t) return "New chat";
  return t.length > 48 ? t.slice(0, 48).trimEnd() + "…" : t;
}

function appendInfo(set: any, get: any, content: string) {
  set({ messages: [...get().messages, { id: newMid(), role: "assistant", content, events: [], local: true }] });
}

// Surface an error to the user as a local assistant note instead of throwing an
// unhandled promise rejection and leaving state stale.
function reportError(get: any, e: any) {
  const msg = e?.message || String(e);
  // eslint-disable-next-line no-console
  console.error("[api]", e);
  appendInfo((p: any) => useStore.setState(p), get, `⚠️ ${msg}`);
  try { useStore.getState().pushToast(msg, "error"); } catch { /* ignore */ }
}

function handleSlash(set: any, get: any, text: string) {
  const [cmd, ...rest] = text.slice(1).split(/\s+/);
  switch (cmd) {
    case "help": return appendInfo(set, get, HELP);
    case "new": return void get().newSession();
    case "export": return get().exportChat();
    case "model":
      if (rest.length >= 2) { get().setTier(rest[0], rest[1]); appendInfo(set, get, `Set ${rest[0]} → ${rest[1]}.`); }
      else appendInfo(set, get, "Usage: /model <tier> <model-id>");
      return;
    case "mode":
      if (["auto", "careful", "trusted"].includes(rest[0])) { get().setMode(rest[0]); appendInfo(set, get, `Approval mode: ${rest[0]}.`); }
      else appendInfo(set, get, "Usage: /mode auto|careful|trusted");
      return;
    default: return appendInfo(set, get, `Unknown command: /${cmd}. Try /help.`);
  }
}

function startRun(set: any, get: any, payload: any, userText: string) {
  const id = get().currentId;
  if (!id || get().running) return;
  closeSocket();
  const userMsg: Msg = { id: newMid(), role: "user", content: userText, events: [] };
  const asst: Msg = { id: newMid(), role: "assistant", content: "", events: [], pending: true };
  // Optimistically bump this chat to "now" (so it sorts into Today, newest-first) and
  // title it if it's still untitled — the server does the same in db, this just avoids
  // the lag so RECENTS updates the instant you send.
  const nowIso = new Date().toISOString();
  const sessionsPatch = get().sessions.map((s: any) => s.id === id
    ? { ...s, updated_at: nowIso, ...((s.title === "New chat" || !s.title) ? { title: deriveTitle(userText) } : {}) }
    : s);
  set({
    messages: [...get().messages, userMsg, asst],
    running: true, cost: 0, pendingApproval: null, pendingPlan: null,
    sessions: sessionsPatch,
  });
  _runStart = Date.now();
  let completed = false;
  const runSession = id;
  socketSession = id;
  let ws: WebSocket;
  try {
    ws = new WebSocket(wsUrl(id));
  } catch (e) {
    reportError(get, e);
    set({ running: false });
    return;
  }
  socket = ws;
  ws.onopen = () =>
    ws.send(JSON.stringify({
      type: "run", mode: get().mode, max_usd: get().maxUsd, max_iterations: get().maxIter, ...payload,
    }));
  ws.onmessage = (e) => {
    // Ignore events from a socket whose session is no longer current.
    if (socketSession !== get().currentId) return;
    let ev: Ev;
    try { ev = JSON.parse(e.data); } catch { return; }
    if (ev.type === "run_complete") completed = true;
    handleEvent(set, get, ev);
  };
  ws.onerror = () => {
    if (socketSession === get().currentId)
      appendToAssistant(set, get, { type: "error", text: "connection error" });
  };
  ws.onclose = () => {
    if (ws !== socket) return;  // a newer run replaced us
    // A socket that drops before run_complete leaves the bubble stuck "pending" —
    // clear it and tell the user the run was interrupted.
    if (!completed && socketSession === get().currentId) {
      patchLastAssistant(set, get, (m) => ({
        ...m, pending: false, live: "",
        content: m.content || "(the run was interrupted — the connection closed before it finished)",
      }));
    }
    set({ running: false });
    socket = null;
    socketSession = null;
  };
}

function appendToAssistant(set: any, get: any, ev: Ev) {
  const msgs = [...get().messages];
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === "assistant") {
      msgs[i] = { ...msgs[i], events: [...msgs[i].events, ev] };
      break;
    }
  }
  set({ messages: msgs });
}

function appendToken(set: any, get: any, piece: string) {
  const msgs = [...get().messages];
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === "assistant") {
      msgs[i] = { ...msgs[i], content: (msgs[i].content || "") + piece, pending: true };
      break;
    }
  }
  set({ messages: msgs });
}

function patchLastAssistant(set: any, get: any, patch: (m: Msg) => Msg) {
  const msgs = [...get().messages];
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === "assistant") { msgs[i] = patch(msgs[i]); break; }
  }
  set({ messages: msgs });
}

function setAssistantContent(set: any, get: any, content: string) {
  const msgs = [...get().messages];
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === "assistant") {
      msgs[i] = { ...msgs[i], content, pending: false };
      break;
    }
  }
  set({ messages: msgs });
}

function handleEvent(set: any, get: any, ev: Ev) {
  switch (ev.type) {
    case "token":
      appendToken(set, get, ev.text || "");
      break;
    case "agent_token":
      patchLastAssistant(set, get, (m) => ({ ...m, live: (m.live || "") + (ev.text || "") }));
      break;
    case "thought":
    case "done":
      patchLastAssistant(set, get, (m) => ({ ...m, live: "" }));  // segment ended
      if (ev.type === "thought") appendToAssistant(set, get, ev);
      break;
    case "final":
      setAssistantContent(set, get, ev.text || "");
      if (ev.cost != null) set({ cost: ev.cost });
      patchLastAssistant(set, get, (m) => ({ ...m, live: "" }));
      break;
    case "approval_request":
      set({ pendingApproval: ev });
      break;
    case "run_complete": {
      const durationMs = _runStart ? Date.now() - _runStart : undefined;
      if (ev.cost != null) set({ cost: ev.cost });
      set({ running: false });
      patchLastAssistant(set, get, (m) => ({
        ...m, live: "",
        meta: { durationMs, tokens: ev.tokens, cost: ev.cost, iterations: ev.iterations,
                cachedTokens: ev.cached_tokens, files: ev.files || [] },
      }));
      closeSocket();
      get().loadFiles().catch((e: any) => reportError(get, e));
      get().loadCheckpoints().catch((e: any) => reportError(get, e));
      get().loadSpend().catch((e: any) => reportError(get, e));
      get().loadTrace().catch((e: any) => reportError(get, e));
      break;
    }
    case "plan":
      appendToAssistant(set, get, ev);
      if (ev.plan_only) set({ pendingPlan: ev.subtasks || [] });
      break;
    case "error":
      appendToAssistant(set, get, ev);
      get().pushToast(ev.text || "Something went wrong.", "error");
      break;
    case "limit":
      appendToAssistant(set, get, ev);
      get().pushToast("Run hit its budget / loop limit.", "info");
      break;
    default:
      appendToAssistant(set, get, ev);
  }
}
