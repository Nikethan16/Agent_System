"""
mcp_server.py — expose Nikki's capabilities to MCP clients (Claude Code, Cursor, …).

Nikki already CONSUMES MCP (tools/mcp.py registers external MCP tools into its toolbelt);
this is the inverse — a stdio MCP SERVER so an external coding tool can call Nikki's
orchestrator, memory, and models AS tools. Newline-delimited JSON-RPC 2.0 over stdin/stdout
(the MCP stdio transport, same framing tools/mcp.py's client speaks). Point your MCP client's
config at:  command = python, args = [-m, server.mcp_server].

Safety model. stdio is a LOCAL, trusted-launcher transport (the client spawns this process),
so there is no network auth here — for remote/HTTP exposure over Tailscale, front it with the
AGENT_AUTH_TOKEN gate (a follow-up). Read-only tools (memory search, agent list, status) and
the answer-synthesis tool (fuse) are always available. The full autonomous run tool is OPT-IN
(AGENT_MCP_ALLOW_RUN=1) and executes with a DENY-RISKY approval hook + a per-call budget cap,
so a caller can never trigger an irreversible/require-human action headlessly.
"""
import os
import sys
import json

PROTOCOL_VERSION = "2024-11-05"
_BUDGET_USD = float(os.environ.get("AGENT_MCP_BUDGET_USD", "0.50"))


# ---- tool handlers (each returns a plain string) --------------------------

def _t_memory_search(query="", k=5):
    from server import memory
    hits = memory.recall(query or "", k=int(k or 5))
    return "\n".join(f"- {h}" for h in hits) if hits else "(no relevant memories found)"


def _t_list_agents():
    from core import agents as _agents
    rows = [f"- {a.id} (tier {a.tier}): {a.when_to_use}".rstrip()
            for a in _agents.agents.agents.values()]
    return "\n".join(rows) or "(no agents configured)"


def _t_status():
    from core.llm import breaker_status
    from core.registry import registry
    out = []
    try:
        act = {t: registry.model_for_tier(t) for t in ("tier1", "tier2", "tier3")}
        out.append("Active model per tier: " + ", ".join(f"{t}={m}" for t, m in act.items()))
    except Exception as e:
        out.append(f"(could not resolve active models: {e})")
    br = breaker_status()
    if br:
        out.append("Circuit breaker (tracked models):")
        out += [f"  {r['model']}: open={r['open']} cooldown={r['cooldown_s']}s fails={r['fails']}"
                for r in br]
    else:
        out.append("Circuit breaker: all clear")
    return "\n".join(out)


def _t_fuse(question=""):
    if not question:
        return "nikki_fuse: 'question' is required"
    from core.llm import Budget
    from core.orchestrator import fuse_task
    return fuse_task(question, budget=Budget(max_usd=_BUDGET_USD))


def _deny_risky(tool, args, decision):
    """Headless approval hook: never allow a require-human / irreversible action."""
    return (False, "headless MCP: risky/irreversible actions are not permitted")


def _t_run_task(task=""):
    if os.environ.get("AGENT_MCP_ALLOW_RUN", "").strip().lower() not in ("1", "true", "yes"):
        return ("Running full autonomous tasks over MCP is disabled. Set AGENT_MCP_ALLOW_RUN=1 to "
                "enable it — risky/irreversible actions are still denied automatically.")
    if not task:
        return "nikki_run_task: 'task' is required"
    from core.llm import Budget
    from core.orchestrator import handle_task
    return handle_task(task, budget=Budget(max_usd=_BUDGET_USD), approve=_deny_risky)


TOOLS = [
    {"name": "nikki_memory_search",
     "description": "Search Nikki's cross-session memory for relevant notes.",
     "inputSchema": {"type": "object",
                     "properties": {"query": {"type": "string"}, "k": {"type": "integer"}},
                     "required": ["query"]},
     "handler": _t_memory_search},
    {"name": "nikki_list_agents",
     "description": "List Nikki's specialist agents and when to use each.",
     "inputSchema": {"type": "object", "properties": {}},
     "handler": _t_list_agents},
    {"name": "nikki_status",
     "description": "Nikki's active model per tier plus circuit-breaker health.",
     "inputSchema": {"type": "object", "properties": {}},
     "handler": _t_status},
    {"name": "nikki_fuse",
     "description": "Answer a hard question by Fusion — ask several models in parallel and "
                    "synthesize one best answer.",
     "inputSchema": {"type": "object", "properties": {"question": {"type": "string"}},
                     "required": ["question"]},
     "handler": _t_fuse},
    {"name": "nikki_run_task",
     "description": "Run Nikki's orchestrator on a task (opt-in via AGENT_MCP_ALLOW_RUN; "
                    "irreversible actions are denied).",
     "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}},
                     "required": ["task"]},
     "handler": _t_run_task},
]
_BY_NAME = {t["name"]: t for t in TOOLS}


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code, msg):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}


def handle_request(req):
    """Dispatch one JSON-RPC request → a response dict, or None for notifications."""
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}
    if method == "initialize":
        return _ok(rid, {"protocolVersion": PROTOCOL_VERSION,
                         "capabilities": {"tools": {}},
                         "serverInfo": {"name": "nikki", "version": "1.0"}})
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        listed = [{k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS]
        return _ok(rid, {"tools": listed})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = _BY_NAME.get(name)
        if not tool:
            return _err(rid, -32602, f"unknown tool: {name}")
        try:
            text = tool["handler"](**args)
        except TypeError as e:
            return _err(rid, -32602, f"bad arguments for {name}: {e}")
        except Exception as e:
            text = f"ERROR: {type(e).__name__}: {e}"
        return _ok(rid, {"content": [{"type": "text", "text": str(text)}]})
    if rid is None:
        return None                      # an unknown notification — no reply
    return _err(rid, -32601, f"method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
