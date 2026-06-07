import { useState } from "react";
import hljs from "highlight.js/lib/common";   // ~35 common languages, much smaller bundle
import "highlight.js/styles/github-dark.css";

export function CodeBlock({ lang, code }: { lang?: string; code: string }) {
  const [copied, setCopied] = useState(false);
  let html = "";
  try {
    html = lang && hljs.getLanguage(lang)
      ? hljs.highlight(code, { language: lang }).value
      : hljs.highlightAuto(code).value;
  } catch {
    html = code.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] as string));
  }
  const copy = () => {
    navigator.clipboard?.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };
  return (
    <div className="my-3 rounded-lg overflow-hidden border border-dark-border bg-[#0d1117]">
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#161b22] border-b border-dark-border">
        <span className="text-[10px] uppercase tracking-wide text-gray-400">{lang || "code"}</span>
        <button onClick={copy} className="text-[10px] uppercase tracking-wide text-gray-400 hover:text-white flex items-center gap-1 transition">
          <span className="material-symbols-outlined text-[14px]">{copied ? "check" : "content_copy"}</span>
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-[13px] leading-relaxed"><code className="hljs" dangerouslySetInnerHTML={{ __html: html }} /></pre>
    </div>
  );
}
