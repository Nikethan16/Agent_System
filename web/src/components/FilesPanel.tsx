import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore } from "../lib/store";
import { api } from "../lib/api";
import { CodeBlock } from "./CodeBlock";
import { Mermaid, Svg } from "./Mermaid";
import { downloadBlob } from "../lib/util";

function iconFor(ext?: string) {
  if ([".py", ".js", ".ts", ".tsx", ".jsx"].includes(ext || "")) return "code";
  if (ext === ".md") return "description";
  if (ext === ".html") return "html";
  if ([".mermaid", ".mmd"].includes(ext || "")) return "schema";
  if ([".png", ".jpg", ".jpeg", ".gif", ".svg"].includes(ext || "")) return "image";
  return "draft";
}

const CODE_EXT = [".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".sh", ".css"];
const LANG: Record<string, string> = {
  ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
  ".jsx": "JavaScript", ".md": "Markdown", ".html": "HTML", ".json": "JSON",
  ".yaml": "YAML", ".yml": "YAML", ".css": "CSS", ".sh": "Shell", ".svg": "SVG",
};
const typeLabel = (ext?: string) => LANG[ext || ""] || (ext ? ext.replace(".", "").toUpperCase() : "File");

function fmtBytes(n?: number): string {
  if (!n && n !== 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const money = (n?: number) => "$" + (n || 0).toFixed(2);

// A clean usage-and-cost mini chart for the workspace panel: today's spend, remaining
// against the daily cap, and a last-7-days spark. Reads /api/spend/overview.
function UsageMini() {
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.spendOverview().then(setD).catch(() => {}); }, []);
  if (!d) return null;
  const hist = (d.history || []).slice(-7);
  const max = Math.max(1e-9, ...hist.map((h: any) => h.usd));
  const cap = d.cap || 0;
  return (
    <div className="mx-4 mt-3 mb-4">
      <p className="text-[10px] uppercase tracking-[0.12em] text-light-muted font-semibold mb-2">Usage &amp; cost</p>
      <div className="border border-light-border dark:border-dark-border rounded-xl p-3 bg-white dark:bg-dark-surface">
        <div className="flex items-baseline gap-2">
          <span className="text-[19px] font-semibold tabular-nums">{money(d.spent_today)}</span>
          <span className="text-[11px] text-light-muted">today{cap > 0 && <> · <span className="text-emerald-600 dark:text-emerald-400">{money(d.remaining)} left</span> of {money(cap)}</>}</span>
        </div>
        <div className="flex items-end gap-1.5 h-14 mt-3">
          {hist.map((h: any, i: number) => (
            <div key={i} title={`${h.day.slice(5)}: ${money(h.usd)}`}
              className="flex-1 rounded-t relative bg-accent-terracotta/15">
              <div className="absolute inset-x-0 bottom-0 rounded-t bg-accent-terracotta"
                style={{ height: `${Math.max(6, (h.usd / max) * 100)}%` }} />
            </div>
          ))}
        </div>
        <div className="flex justify-between mt-1.5 text-[9px] text-light-muted font-code">
          <span>{hist[0]?.day?.slice(5)}</span><span>today</span>
        </div>
      </div>
    </div>
  );
}

function DiffView({ text }: { text: string }) {
  if (!text.trim()) return <div className="text-light-muted text-xs">No changes vs the last checkpoint.</div>;
  return (
    <pre className="font-code text-[12px] leading-5 overflow-x-auto">
      {text.split("\n").map((ln, i) => {
        let c = "text-on-surface-variant dark:text-light-muted";
        if (ln.startsWith("+") && !ln.startsWith("+++")) c = "text-emerald-600 dark:text-emerald-400";
        else if (ln.startsWith("-") && !ln.startsWith("---")) c = "text-red-500";
        else if (ln.startsWith("@@")) c = "text-blue-500";
        return <div key={i} className={c}>{ln || " "}</div>;
      })}
    </pre>
  );
}

// Live HTML preview. Fetches a BUNDLED version (local CSS/JS/images inlined by the
// server) so a multi-file app renders fully — srcDoc alone can't load sibling files.
// Falls back to the raw file content if the bundle call fails.
function HtmlPreview({ id, path, fallback }: { id: string | null; path: string; fallback: string }) {
  const [html, setHtml] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setHtml(null);
    if (id) api.previewHtml(id, path).then((r) => live && setHtml(r?.html ?? fallback)).catch(() => live && setHtml(fallback));
    else setHtml(fallback);
    return () => { live = false; };
  }, [id, path]);
  return <iframe sandbox="allow-scripts" srcDoc={html ?? "<!doctype html><body style='font:14px system-ui;color:#888;padding:12px'>Loading preview…"}
    title="preview" className="w-full h-full min-h-[300px] bg-white rounded-lg border border-light-border" />;
}

function Body({ sel, view, diff, id }: { sel: any; view: string; diff: string; id: string | null }) {
  const isHtml = sel.ext === ".html";
  const isMd = sel.ext === ".md";
  const isMermaid = [".mermaid", ".mmd"].includes(sel.ext || "");
  const isSvg = sel.ext === ".svg";
  const isImage = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"].includes(sel.ext || "");
  const isPdf = sel.ext === ".pdf";
  const lang = (sel.ext || "").replace(".", "") || undefined;
  // Binary artifacts (images, PDFs) render straight from /file/raw.
  if (isImage && id) return <img src={api.rawFileUrl(id, sel.path)} alt={sel.path} className="max-w-full rounded-lg border border-light-border dark:border-dark-border" />;
  if (isPdf && id) return <iframe src={api.rawFileUrl(id, sel.path)} title="pdf" className="w-full h-full min-h-[420px] rounded-lg border border-light-border bg-white" />;
  if (sel.binary) return <div className="text-light-muted text-xs">Binary file ({sel.ext}). {id && <a className="text-accent-terracotta underline" href={api.rawFileUrl(id, sel.path)} target="_blank" rel="noreferrer">Open raw</a>}</div>;
  if (view === "diff") return <DiffView text={diff} />;
  if (view === "preview" && isHtml) return <HtmlPreview id={id} path={sel.path} fallback={sel.content || ""} />;
  if (view === "preview" && isMd) return <div className="prose-msg text-sm"><ReactMarkdown remarkPlugins={[remarkGfm]}>{sel.content || ""}</ReactMarkdown></div>;
  if (view === "preview" && isMermaid) return <Mermaid code={sel.content || ""} />;
  if (view === "preview" && isSvg) return <Svg markup={sel.content || ""} />;
  return <CodeBlock lang={lang} code={sel.content || ""} />;
}

type Version = { checkpoint: string; label: string; created_at?: string | null; exists: boolean; size: number };

function HistoryView({ id, path }: { id: string; path: string }) {
  const [versions, setVersions] = useState<Version[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const lang = (path.match(/\.[^.]+$/)?.[0] || "").replace(".", "") || undefined;

  useEffect(() => {
    setActive(null); setContent("");
    api.fileVersions(id, path).then((r) => setVersions(r.versions || []));
  }, [id, path]);

  const pick = (v: Version) => {
    setActive(v.checkpoint);
    api.fileAt(id, path, v.checkpoint).then((r) => setContent(r.binary ? "(binary file)" : (r.content || "")));
  };

  if (!versions.length) return <div className="text-light-muted text-xs">No version history yet.</div>;
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        {versions.map((v, i) => (
          <button key={v.checkpoint} onClick={() => pick(v)}
            className={`w-full text-left flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs transition ${active === v.checkpoint ? "border-accent-terracotta/60 bg-accent-terracotta/5" : "border-light-border dark:border-dark-border hover:border-accent-terracotta/30"}`}>
            <span className="material-symbols-outlined text-[15px] text-accent-terracotta">
              {i === 0 ? "radio_button_checked" : "history"}
            </span>
            <span className="flex-1 truncate">{i === 0 ? "Current" : v.label}</span>
            <span className="text-[10px] text-light-muted">{v.size}b</span>
          </button>
        ))}
      </div>
      {active && (
        <div className="border-t border-light-border dark:border-dark-border pt-3">
          <CodeBlock lang={lang} code={content} />
        </div>
      )}
    </div>
  );
}

export default function FilesPanel() {
  const { files, selected, openFile, loadFiles, currentId, messages } = useStore();

  // Files touched by the most recent run (with +/- deltas) get their own section so
  // "what changed just now" is separated from the rest of the workspace.
  const lastChanges = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const f = messages[i]?.meta?.files;
      if (f && f.length) return f;
    }
    return [] as { path: string; status: string; added: number; removed: number }[];
  })();
  const changeMap = new Map(lastChanges.map((c) => [c.path, c]));
  const changed = files.filter((f) => changeMap.has(f.path));
  const context = files.filter((f) => !changeMap.has(f.path));
  const [view, setView] = useState<"source" | "preview" | "diff" | "history">("source");
  const [diff, setDiff] = useState("");
  const [expanded, setExpanded] = useState(false);
  const isHtml = selected?.ext === ".html";
  const isMd = selected?.ext === ".md";
  const isMermaid = [".mermaid", ".mmd"].includes(selected?.ext || "");
  const isSvg = selected?.ext === ".svg";
  const isImage = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"].includes(selected?.ext || "");
  const isPdf = selected?.ext === ".pdf";
  const previewable = isHtml || isMd || isMermaid || isSvg || isImage || isPdf;

  useEffect(() => { setView(previewable ? "preview" : "source"); }, [selected?.path]);
  useEffect(() => {
    if (view === "diff" && selected && currentId) api.fileDiff(currentId, selected.path).then((r) => setDiff(r.diff || ""));
  }, [view, selected?.path, currentId]);

  const copy = () => selected && navigator.clipboard?.writeText(selected.content || "");
  const download = () => {
    if (!selected) return;
    const name = selected.path.split("/").pop() || "file";
    if (selected.binary && currentId) {
      // Images/PDFs have no text content — download the raw bytes via /file/raw.
      const a = document.createElement("a");
      a.href = api.rawFileUrl(currentId, selected.path);
      a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
    } else {
      downloadBlob(name, selected.content || "");
    }
  };

  const Tab = ({ id, label }: { id: any; label: string }) => (
    <button onClick={() => setView(id)}
      className={`px-2.5 py-1 text-[11px] capitalize rounded-md transition ${view === id ? "bg-white dark:bg-dark-surface text-on-surface dark:text-dark-text shadow-sm font-semibold" : "text-light-muted hover:text-on-surface dark:hover:text-dark-text"}`}>{label}</button>
  );
  const TabGroup = ({ children }: { children: any }) => (
    <div className="flex items-center gap-0.5 bg-surface-container-low dark:bg-dark-bg rounded-lg p-0.5">{children}</div>
  );
  const IconBtn = ({ icon, on, title }: { icon: string; on: () => void; title: string }) => (
    <button onClick={on} title={title} className="p-1 rounded-md text-light-muted hover:text-on-surface dark:hover:text-dark-text hover:bg-surface-container-low dark:hover:bg-dark-bg transition">
      <span className="material-symbols-outlined text-[16px]">{icon}</span>
    </button>
  );

  const Section = ({ label, count }: { label: string; count: number }) => (
    <div className="flex items-center gap-2 px-4 pt-3 pb-1">
      <span className="text-[10px] uppercase tracking-[0.12em] text-light-muted font-semibold">{label}</span>
      <span className="text-[10px] font-code text-light-muted">{count}</span>
      <span className="flex-1 h-px bg-light-border/60 dark:bg-dark-border" />
    </div>
  );

  const FileRow = ({ f }: { f: any }) => {
    const isCode = CODE_EXT.includes(f.ext || "");
    const ch = changeMap.get(f.path);
    return (
      <div onClick={() => openFile(f.path)}
        className={`group flex items-center gap-3 px-4 py-2 cursor-pointer transition ${selected?.path === f.path ? "bg-accent-terracotta/8" : "hover:bg-surface-container-low dark:hover:bg-dark-bg"}`}>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${isCode ? "bg-accent-terracotta/12 text-accent-terracotta" : "bg-surface-container dark:bg-dark-bg text-light-muted"}`}>
          <span className="material-symbols-outlined text-[16px]">{iconFor(f.ext)}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className={`text-[13px] truncate ${selected?.path === f.path ? "font-semibold" : "font-medium"}`}>{f.path}</div>
          <div className="text-[11px] text-light-muted truncate">{fmtBytes(f.size)} · {typeLabel(f.ext)}</div>
        </div>
        {ch && (ch.added > 0 || ch.removed > 0) && (
          <div className="font-code text-[11px] text-right shrink-0 tabular-nums">
            {ch.added > 0 && <span className="text-emerald-600 dark:text-emerald-400">+{ch.added}</span>}
            {ch.added > 0 && ch.removed > 0 && " "}
            {ch.removed > 0 && <span className="text-red-500">−{ch.removed}</span>}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <h4 className="text-[13px] font-semibold">Workspace</h4>
        <IconBtn icon="refresh" on={() => loadFiles()} title="Refresh" />
      </div>
      <div className="overflow-y-auto scrollbar" style={{ maxHeight: selected ? "45%" : "100%" }}>
        <Section label="Project files" count={files.length} />
        {files.length === 0 && <div className="text-light-muted text-xs px-5 py-2">No files yet — anything the agents build lands here.</div>}
        {changed.length > 0 && <Section label="Changed this run" count={changed.length} />}
        {changed.map((f) => <FileRow key={f.path} f={f} />)}
        {context.length > 0 && changed.length > 0 && <Section label="Context" count={context.length} />}
        {context.map((f) => <FileRow key={f.path} f={f} />)}
        <UsageMini />
      </div>

      {selected && (
        <div className="flex-1 border-t border-light-border dark:border-dark-border mt-2 flex flex-col min-h-0">
          <div className="flex items-center gap-2 px-4 pt-2.5 pb-0.5">
            <span className="material-symbols-outlined text-[15px] text-accent-terracotta">{iconFor(selected.ext)}</span>
            <span className="text-[12.5px] font-code font-medium truncate">{selected.path}</span>
            <span className="text-[10px] text-light-muted ml-auto shrink-0">{typeLabel(selected.ext)}</span>
          </div>
          <div className="flex items-center gap-1 px-4 py-2 border-b border-light-border dark:border-dark-border">
            <TabGroup>
              <Tab id="source" label="source" />
              {previewable && <Tab id="preview" label="preview" />}
              <Tab id="diff" label="diff" />
              <Tab id="history" label="history" />
            </TabGroup>
            <div className="ml-auto flex items-center gap-0.5">
              <IconBtn icon="content_copy" on={copy} title="Copy" />
              <IconBtn icon="download" on={download} title="Download" />
              <IconBtn icon="open_in_full" on={() => setExpanded(true)} title="Expand to canvas" />
            </div>
          </div>
          <div className="flex-1 overflow-auto scrollbar p-4">
            {view === "history" && currentId
              ? <HistoryView id={currentId} path={selected.path} />
              : <Body sel={selected} view={view} diff={diff} id={currentId} />}
          </div>
        </div>
      )}

      {expanded && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-6" onClick={() => setExpanded(false)}>
          <div className="w-full max-w-4xl h-[85vh] bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-2xl flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 px-5 py-3 border-b border-light-border dark:border-dark-border">
              <span className="material-symbols-outlined text-accent-terracotta text-[20px]">{iconFor(selected.ext)}</span>
              <span className="font-semibold flex-1 truncate">{selected.path}</span>
              <Tab id="source" label="source" />
              {previewable && <Tab id="preview" label="preview" />}
              <Tab id="diff" label="diff" />
              <Tab id="history" label="history" />
              <IconBtn icon="content_copy" on={copy} title="Copy" />
              <IconBtn icon="download" on={download} title="Download" />
              <IconBtn icon="close" on={() => setExpanded(false)} title="Close" />
            </div>
            <div className="flex-1 overflow-auto scrollbar p-6">
              {view === "history" && currentId
                ? <HistoryView id={currentId} path={selected.path} />
                : <Body sel={selected} view={view} diff={diff} id={currentId} />}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
