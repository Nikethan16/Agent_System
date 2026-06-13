import { useEffect, useState } from "react";
import { api } from "../lib/api";

const PROVIDERS = ["nvidia_nim", "gemini", "openrouter", "openai", "anthropic", "deepseek"];
const inp =
  "bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-lg px-2 py-1 text-sm outline-none";

// Settings → Fleet: manage the API-key pool + the fallback routing chains.
export default function FleetPanel() {
  const [keys, setKeys] = useState<Record<string, any[]>>({});
  const [routing, setRouting] = useState<{ routing: Record<string, string[]> }>({ routing: {} });
  const [catalog, setCatalog] = useState<any[]>([]);
  const [provider, setProvider] = useState("nvidia_nim");
  const [keyVal, setKeyVal] = useState("");
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [nm, setNm] = useState({ id: "", tier_hint: "2", good_for: "", cost: "1", context_window: "" });
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");

  const load = async () => {
    try { setKeys(await api.keys()); } catch { /* empty */ }
    try { setRouting(await api.routing()); } catch { /* empty */ }
    try { setCatalog((await api.models()).catalog || []); } catch { /* empty */ }
  };
  useEffect(() => { load(); }, []);

  const addModel = async () => {
    if (!nm.id.trim().includes("/")) { setMsg("model id should be a full LiteLLM string, e.g. nvidia_nim/vendor/model"); return; }
    setBusy("model"); setMsg("");
    try {
      await api.addCatalogModel({
        id: nm.id.trim(),
        provider: nm.id.split("/")[0],
        requires_env: { nvidia_nim: "NVIDIA_NIM_API_KEY", gemini: "GEMINI_API_KEY", openrouter: "OPENROUTER_API_KEY", openai: "OPENAI_API_KEY", anthropic: "ANTHROPIC_API_KEY", deepseek: "DEEPSEEK_API_KEY" }[nm.id.split("/")[0]] || null,
        free: true,
        cost: parseInt(nm.cost) || 1,
        tier_hint: parseInt(nm.tier_hint) || 2,
        good_for: nm.good_for.split(",").map((s) => s.trim()).filter(Boolean),
        ...(nm.context_window ? { context_window: parseInt(nm.context_window) } : {}),
      });
      setNm({ id: "", tier_hint: "2", good_for: "", cost: "1", context_window: "" });
      load();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(""); }
  };
  const removeModel = async (id: string) => { try { await api.removeCatalogModel(id); load(); } catch (e: any) { setMsg(e.message); } };

  const add = async () => {
    if (keyVal.trim().length < 6) { setMsg("key looks too short"); return; }
    setBusy("add"); setMsg("");
    try { setKeys(await api.addKey(provider, keyVal.trim())); setKeyVal(""); }
    catch (e: any) { setMsg(e.message); } finally { setBusy(""); }
  };
  const remove = async (p: string, masked: string) => {
    try { setKeys(await api.removeKey(p, masked)); } catch (e: any) { setMsg(e.message); }
  };
  const test = async (p: string) => {
    setBusy("test:" + p); setMsg("");
    try { const r = await api.testKey(p); setMsg(r.ok ? `✓ ${p}: ${r.reply}` : `✗ ${p}: ${r.error}`); }
    catch (e: any) { setMsg(e.message); } finally { setBusy(""); }
  };
  const saveChain = async (tt: string) => {
    const chain = (edit[tt] ?? (routing.routing[tt] || []).join("\n"))
      .split("\n").map((s) => s.trim()).filter(Boolean);
    setBusy("route:" + tt);
    try { const r = await api.setRouting(tt, chain); setRouting({ routing: r.routing }); setMsg(`saved ${tt}`); }
    catch (e: any) { setMsg(e.message); } finally { setBusy(""); }
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="text-sm font-medium mb-1">API keys (pool)</div>
        <div className="text-[11px] text-light-muted mb-3">
          Add more free accounts' keys to raise throughput — the pool spreads calls across them
          (least-loaded, ~40 rpm each). Keys are masked + stored server-side, never shown in full.
        </div>
        {Object.keys(keys).length === 0 && (
          <div className="text-xs text-light-muted mb-2">No keys yet — add one below, or set them in <code>.env</code>.</div>
        )}
        {Object.entries(keys).map(([p, list]) => (
          <div key={p} className="mb-3">
            <div className="flex items-center justify-between">
              <div className="text-xs font-medium">{p} <span className="text-light-muted">· {list.length} key(s)</span></div>
              <button onClick={() => test(p)} disabled={!!busy}
                className="text-[11px] px-2 py-0.5 rounded border border-light-border dark:border-dark-border hover:bg-surface-container-low dark:hover:bg-dark-bg">
                {busy === "test:" + p ? "testing…" : "Test"}
              </button>
            </div>
            {list.map((k: any) => (
              <div key={k.key} className="flex items-center justify-between gap-2 text-[11px] py-1 pl-2">
                <span className="font-code">{k.key}</span>
                <span className="text-light-muted flex-1 text-right">
                  {k.used}/{k.rpm} rpm{k.cooldown_s > 0 ? ` · cooldown ${k.cooldown_s}s` : ""}{!k.enabled ? " · disabled" : ""}
                </span>
                {k.removable
                  ? <button onClick={() => remove(p, k.key)} aria-label="remove key"
                      className="material-symbols-outlined text-[15px] text-light-muted hover:text-red-500">delete</button>
                  : <span className="text-[10px] text-light-muted w-10 text-right">.env</span>}
              </div>
            ))}
          </div>
        ))}
        <div className="flex items-center gap-2 mt-2">
          <select value={provider} onChange={(e) => setProvider(e.target.value)} className={inp}>
            {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <input value={keyVal} onChange={(e) => setKeyVal(e.target.value)} placeholder="paste API key" type="password" className={inp + " flex-1"} />
          <button onClick={add} disabled={!!busy} className="text-sm px-3 py-1 rounded-lg bg-accent-terracotta text-white disabled:opacity-50">
            {busy === "add" ? "…" : "Add"}
          </button>
        </div>
      </div>

      <div>
        <div className="text-sm font-medium mb-1">Catalog models (add + when-to-use)</div>
        <div className="text-[11px] text-light-muted mb-3">
          Add any model a provider offers. <b>good_for</b> tags + <b>tier</b> are the "when to use" signals
          the cost-first picker reads; new models slot into the fallback chains automatically.
        </div>
        <div className="max-h-40 overflow-y-auto scrollbar mb-2">
          {catalog.map((m) => (
            <div key={m.id} className="flex items-center justify-between gap-2 text-[11px] py-0.5">
              <span className="font-code truncate">{m.id}</span>
              <span className="text-light-muted shrink-0">t{m.tier_hint} · {(m.good_for || []).slice(0, 3).join(",")}</span>
              <button onClick={() => removeModel(m.id)} aria-label="remove model"
                className="material-symbols-outlined text-[14px] text-light-muted hover:text-red-500">delete</button>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2 mb-6">
          <input value={nm.id} onChange={(e) => setNm({ ...nm, id: e.target.value })} placeholder="provider/vendor/model" className={inp + " col-span-2"} />
          <input value={nm.good_for} onChange={(e) => setNm({ ...nm, good_for: e.target.value })} placeholder="good_for (comma: coding,research)" className={inp + " col-span-2"} />
          <select value={nm.tier_hint} onChange={(e) => setNm({ ...nm, tier_hint: e.target.value })} className={inp}>
            <option value="1">tier 1 (simple)</option><option value="2">tier 2 (balanced)</option><option value="3">tier 3 (frontier)</option>
          </select>
          <input value={nm.cost} onChange={(e) => setNm({ ...nm, cost: e.target.value })} placeholder="cost rank (0=preferred)" className={inp} />
          <input value={nm.context_window} onChange={(e) => setNm({ ...nm, context_window: e.target.value })} placeholder="context window (optional)" className={inp} />
          <button onClick={addModel} disabled={!!busy} className="text-sm px-3 py-1 rounded-lg bg-accent-terracotta text-white disabled:opacity-50">
            {busy === "model" ? "…" : "Add model"}
          </button>
        </div>
      </div>

      <div>
        <div className="text-sm font-medium mb-1">Routing &amp; fallback chains</div>
        <div className="text-[11px] text-light-muted mb-3">
          Per task type: the models tried in order (primary first; the rest are automatic fallbacks
          if one is rate-limited or down). One model id per line.
        </div>
        {Object.keys(routing.routing).length === 0 && <div className="text-xs text-light-muted">Loading…</div>}
        {Object.entries(routing.routing).map(([tt, chain]) => (
          <div key={tt} className="mb-3 border-b border-light-border dark:border-dark-border pb-3">
            <div className="text-xs font-medium mb-1">{tt}</div>
            <textarea defaultValue={(chain as string[]).join("\n")}
              onChange={(e) => setEdit({ ...edit, [tt]: e.target.value })}
              className={inp + " w-full font-code text-[11px]"} rows={Math.max(2, (chain as string[]).length)} />
            <div className="flex justify-end mt-1">
              <button onClick={() => saveChain(tt)} disabled={!!busy}
                className="text-[11px] px-2 py-0.5 rounded border border-light-border dark:border-dark-border hover:bg-surface-container-low dark:hover:bg-dark-bg">
                {busy === "route:" + tt ? "saving…" : "Save"}
              </button>
            </div>
          </div>
        ))}
      </div>
      {msg && <div className="text-[11px] text-light-muted">{msg}</div>}
    </div>
  );
}
