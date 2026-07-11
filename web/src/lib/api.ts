// ---- auth token (only needed when the server is deployed off-localhost) ----
const TOKEN_KEY = "agent_auth_token";
export const getAuthToken = () => localStorage.getItem(TOKEN_KEY) || "";
export const setAuthToken = (t: string) => {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
};

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra || {}) };
  const t = getAuthToken();
  if (t) h["X-Auth-Token"] = t;
  return h;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

// Single choke point for every request: attaches auth, checks response.ok, and
// turns a non-2xx / network failure into a descriptive ApiError instead of a
// silent rejected .json().
async function request(url: string, init: RequestInit = {}): Promise<any> {
  let res: Response;
  try {
    res = await fetch(url, { ...init, headers: authHeaders(init.headers as Record<string, string>) });
  } catch (e: any) {
    throw new ApiError(0, `network error: ${e?.message || e}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail || JSON.stringify(body);
    } catch {
      /* non-JSON body */
    }
    throw new ApiError(res.status, `${res.status}: ${detail}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

const GET = (url: string) => request(url);
const POST = (url: string, body: any) =>
  request(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const PATCH = (url: string, body: any) =>
  request(url, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const PUT = (url: string, body: any) =>
  request(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const DELETE = (url: string) => request(url, { method: "DELETE" });
const UPLOAD = (url: string, file: File) => {
  const fd = new FormData();
  fd.append("file", file);
  return request(url, { method: "POST", body: fd });
};

export const api = {
  // auth: email+password login gate (optional — see server/auth_routes.py)
  authConfig: () => GET("/api/auth/config"),
  login: (email: string, password: string) => POST("/api/login", { email, password }),
  me: () => GET("/api/me"),

  models: () => GET("/api/models"),
  agents: () => GET("/api/agents"),
  // Skills Hub: list local skills (with enabled/source), the allowlisted sources, and
  // sync/enable/disable controls. Synced skills arrive disabled (review gate).
  skills: () => GET("/api/skills").then((r: any) => r?.skills || []),
  skillSources: () => GET("/api/skills/sources").then((r: any) => r?.sources || []),
  skillsAvailable: (source: string) =>
    GET(`/api/skills/available?source=${encodeURIComponent(source)}`).then((r: any) => r?.available || []),
  skillView: (name: string) => GET(`/api/skills/${encodeURIComponent(name)}`),
  skillSync: (source: string, name: string) => POST("/api/skills/sync", { source, name }),
  skillEnable: (name: string) => POST(`/api/skills/${encodeURIComponent(name)}/enable`, {}),
  skillDisable: (name: string) => POST(`/api/skills/${encodeURIComponent(name)}/disable`, {}),
  spend: () => GET("/api/spend"),
  spendOverview: () => GET("/api/spend/overview"),
  setTier: (tier: string, model: string) => POST("/api/models/tier", { tier, model }),
  // Per-use-case routing: which ordered model chain serves each task type (editable,
  // persisted to data/routing.json, survives deploys).
  getRouting: () => GET("/api/models/routing"),
  setRouting: (task_type: string, chain: string[]) =>
    POST("/api/models/routing", { task_type, chain }),
  resetRouting: (task_type: string) => DELETE(`/api/models/routing/${encodeURIComponent(task_type)}`),
  scout: () => POST("/api/models/scout", {}),
  applyCatalog: (models: any[]) => POST("/api/models/catalog", { models }),

  listSessions: (project_id?: string) =>
    GET("/api/sessions" + (project_id ? `?project_id=${encodeURIComponent(project_id)}` : "")),
  createSession: (title = "New chat", project_id = "") => POST("/api/sessions", { title, project_id }),

  listProjects: () => GET("/api/projects"),
  createProject: (name: string) => POST("/api/projects", { name }),
  updateProject: (pid: string, body: any) => PATCH(`/api/projects/${pid}`, body),
  deleteProject: (pid: string) => DELETE(`/api/projects/${pid}`),
  projectFiles: (pid: string) => GET(`/api/projects/${pid}/files`),
  addProjectFile: (pid: string, file: File) => UPLOAD(`/api/projects/${pid}/files`, file),
  removeProjectFile: (pid: string, name: string) =>
    DELETE(`/api/projects/${pid}/files/${encodeURIComponent(name)}`),

  renameSession: (id: string, title: string) => PATCH(`/api/sessions/${id}`, { title }),
  star: (id: string) => POST(`/api/sessions/${id}/star`, {}),
  feedback: (id: string, value: string) => POST(`/api/sessions/${id}/feedback`, { value }),
  deleteSession: (id: string) => DELETE(`/api/sessions/${id}`),
  messages: (id: string) => GET(`/api/sessions/${id}/messages`),

  upload: (id: string, file: File) => UPLOAD(`/api/sessions/${id}/upload`, file),
  truncate: (id: string, keep: number) => POST(`/api/sessions/${id}/truncate`, { keep }),

  jobs: (sessionId: string) => GET(`/api/jobs?session_id=${encodeURIComponent(sessionId)}`),
  enqueue: (session_id: string, text: string, max_usd = 0.5, max_iterations = 12) =>
    POST("/api/enqueue", { session_id, text, max_usd, max_iterations }),

  checkpoints: (id: string) => GET(`/api/sessions/${id}/checkpoints`),
  restore: (id: string, checkpoint_id: string) => POST(`/api/sessions/${id}/restore`, { checkpoint_id }),

  memory: (scope?: string) => GET("/api/memory" + (scope ? `?scope=${encodeURIComponent(scope)}` : "")),
  addFact: (text: string, key: string, scope = "global") => POST("/api/memory", { text, key, scope }),
  forgetFact: (id: string) => DELETE(`/api/memory/${id}`),

  rules: (status?: string) => GET("/api/memory/rules" + (status ? `?status=${encodeURIComponent(status)}` : "")),
  addRule: (text: string, scope = "global") => POST("/api/memory/rules", { text, scope }),
  approveRule: (id: string) => POST(`/api/memory/rules/${id}/approve`, {}),
  deleteRule: (id: string) => DELETE(`/api/memory/rules/${id}`),

  benchmarkCases: () => GET("/api/benchmark/cases"),
  benchmarkRuns: () => GET("/api/benchmark/runs"),
  startBenchmark: (model: string, mode: string) => POST("/api/benchmark/run", { model, mode }),

  // fleet management: API-key pool, fallback routing, per-key usage/health
  keys: () => GET("/api/keys"),
  addKey: (provider: string, key: string) => POST("/api/keys", { provider, key }),
  removeKey: (provider: string, masked: string) =>
    DELETE(`/api/keys/${encodeURIComponent(provider)}/${encodeURIComponent(masked)}`),
  testKey: (provider: string) => POST("/api/keys/test", { provider }),
  usage: () => GET("/api/usage"),
  routing: () => GET("/api/routing"),
  setRouting: (task_type: string, chain: string[]) => PUT("/api/routing", { task_type, chain }),
  addCatalogModel: (model: any) => POST("/api/models/catalog", { models: [model] }),
  removeCatalogModel: (id: string) => DELETE("/api/models/catalog/" + id),

  // run trace: reconstructed span tree (subagents/tools/cost) from the JSONL log
  traces: (id: string) => GET(`/api/traces/${id}`),

  // model health: per-key usage + per-model call metrics + cache hit-rates
  fleetHealth: () => GET("/api/fleet/health"),
  resetHealth: () => POST("/api/fleet/health/reset", {}),

  // unattended runs: reattach to an in-flight run + answer approvals later
  activeRun: (id: string) => GET(`/api/sessions/${id}/active-run`),
  approvals: (id: string) => GET(`/api/sessions/${id}/approvals`),
  resolveApproval: (reqId: string, allowed: boolean, reason = "") =>
    POST(`/api/approvals/${reqId}/resolve`, { allowed, reason }),

  // scheduled tasks (once/interval/daily/weekly)
  schedules: (session_id?: string) =>
    GET("/api/schedules" + (session_id ? `?session_id=${encodeURIComponent(session_id)}` : "")),
  createSchedule: (body: { session_id: string; text: string; kind: string; spec: string }) =>
    POST("/api/schedules", body),
  toggleSchedule: (sid: string) => POST(`/api/schedules/${sid}/toggle`, {}),
  runSchedule: (sid: string) => POST(`/api/schedules/${sid}/run`, {}),
  deleteSchedule: (sid: string) => DELETE(`/api/schedules/${sid}`),

  // project roadmap (resumable state)
  state: (sessionId: string) => GET(`/api/memory/state/${sessionId}`),
  clearState: (sessionId: string) => DELETE(`/api/memory/state/${sessionId}`),

  files: (id: string) => GET(`/api/sessions/${id}/files`),
  readFile: (id: string, path: string) =>
    GET(`/api/sessions/${id}/file?path=${encodeURIComponent(path)}`),
  fileVersions: (id: string, path: string) =>
    GET(`/api/sessions/${id}/file/versions?path=${encodeURIComponent(path)}`),
  fileAt: (id: string, path: string, checkpoint: string) =>
    GET(`/api/sessions/${id}/file/at?path=${encodeURIComponent(path)}&checkpoint=${encodeURIComponent(checkpoint)}`),
  fileDiff: (id: string, path: string) =>
    GET(`/api/sessions/${id}/file/diff?path=${encodeURIComponent(path)}`),
  rawFileUrl: (id: string, path: string) =>
    `/api/sessions/${id}/file/raw?path=${encodeURIComponent(path)}`,
};

export const wsUrl = (id: string) => {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const t = getAuthToken();
  const q = t ? `?token=${encodeURIComponent(t)}` : "";
  return `${scheme}://${location.host}/api/ws/${id}${q}`;
};
