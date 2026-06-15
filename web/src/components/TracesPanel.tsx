import { useEffect, useState } from "react";
import { useStore } from "../lib/store";

// RightPanel → Trace. The reconstructed span tree for this chat's last run:
// the LEAD loop → subagent spans → tool calls, with cost/tokens/duration per node.
// Read-only; rebuilt server-side from the always-on JSONL trace.

const KIND_ICON: Record<string, string> = {
  run: "account_tree", agent: "smart_toy", tool: "build",
};

function fmtDur(ms?: number | null): string {
  if (ms == null) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function chips(node: any): string[] {
  const out: string[] = [];
  const d = fmtDur(node.duration_ms);
  if (d) out.push(d);
  if (node.tokens) out.push(`${node.tokens.toLocaleString()} tok`);
  if (node.cost) out.push(`$${Number(node.cost).toFixed(4)}`);
  return out;
}

function Node({ node, depth }: { node: any; depth: number }) {
  const hasKids = (node.children?.length || 0) > 0;
  const [open, setOpen] = useState(depth < 2);
  const icon = KIND_ICON[node.kind] || "circle";
  return (
    <div>
      <div
        className="flex items-start gap-1.5 py-1 rounded-md hover:bg-surface-container-low dark:hover:bg-dark-bg cursor-pointer"
        style={{ paddingLeft: `${depth * 12}px` }}
        onClick={() => hasKids && setOpen(!open)}
      >
        <span className="material-symbols-outlined text-[13px] text-light-muted mt-0.5 w-3.5">
          {hasKids ? (open ? "expand_more" : "chevron_right") : ""}
        </span>
        <span className="material-symbols-outlined text-[13px] text-accent-terracotta mt-0.5">{icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 text-[11px]">
            <span className="text-on-surface dark:text-dark-text font-code truncate">{node.name}</span>
            {chips(node).map((c, i) => (
              <span key={i} className="text-[10px] text-light-muted">{c}</span>
            ))}
          </div>
          {node.subtask && (
            <p className="text-[10px] text-light-muted truncate leading-snug">{node.subtask}</p>
          )}
          {node.args && (
            <code className="block text-[10px] text-light-muted truncate">{node.args}</code>
          )}
        </div>
      </div>
      {open && hasKids && node.children.map((c: any, i: number) => (
        <Node key={i} node={c} depth={depth + 1} />
      ))}
    </div>
  );
}

export default function TracesPanel() {
  const { trace, loadTrace, currentId } = useStore();
  useEffect(() => { loadTrace(); }, [currentId]);

  const tree = trace?.tree;
  const totals = trace?.totals;
  const empty = !tree || ((tree.children?.length || 0) === 0 && (tree.events?.length || 0) === 0);

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-widest text-light-muted">Run trace</p>
        <button onClick={() => loadTrace()} title="Refresh" aria-label="Refresh trace"
          className="p-1 rounded-md text-light-muted hover:text-on-surface dark:hover:text-dark-text transition">
          <span className="material-symbols-outlined text-[15px]">refresh</span>
        </button>
      </div>
      <p className="text-[11px] text-light-muted leading-relaxed">
        The span tree for this chat's runs — subagents, tool calls, and the cost/tokens/time of each step.
      </p>
      {totals && (totals.cost || totals.tokens || totals.duration_ms) && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-light-muted border-b border-light-border dark:border-dark-border pb-2">
          {totals.duration_ms != null && <span>{fmtDur(totals.duration_ms)}</span>}
          {totals.tokens ? <span>{totals.tokens.toLocaleString()} tokens</span> : null}
          {totals.cost ? <span>${Number(totals.cost).toFixed(4)}</span> : null}
        </div>
      )}
      {empty ? (
        <p className="text-[11px] text-light-muted italic">No trace yet — run a turn to populate it.</p>
      ) : (
        <div className="text-xs">
          <Node node={tree} depth={0} />
        </div>
      )}
    </div>
  );
}
