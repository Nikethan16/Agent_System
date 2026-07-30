"""
mcp.py — a real MCP (Model Context Protocol) adapter: the "connect anything" path.

On import it reads config/mcp.yaml, launches each configured MCP server (stdio
transport), performs the JSON-RPC handshake, lists the server's tools, and registers
each one into the tool registry as `mcp__<server>__<tool>` — so an external connector
becomes an agent tool with our risk labels + per-agent grants. The security gate
applies to MCP tools exactly like any other tool.

Transport: newline-delimited JSON-RPC 2.0 over the server's stdin/stdout. A background
reader thread dispatches responses by id, so calls have timeouts and never hang import.
"""
import os
import sys
import json
import threading
import subprocess

import yaml

from core import toolbelt
from core.agents import agents as agent_registry
from core.boundary import wrap as _wrap_untrusted

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG = os.environ.get("MCP_CONFIG", os.path.join(_BASE, "config", "mcp.yaml"))

_RISK = {"safe": toolbelt.RISK_SAFE, "write": toolbelt.RISK_WRITE, "critical": toolbelt.RISK_CRITICAL}

_clients: dict[str, "MCPClient"] = {}


class MCPClient:
    def __init__(self, name, command, args, cwd=None):
        self.name = name
        cmd = sys.executable if command in ("python", "python3") else command
        self.proc = subprocess.Popen(
            [cmd, *args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, cwd=cwd or _BASE,
        )
        self._id = 0
        self._id_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending: dict[int, dict] = {}
        self._alive = True
        threading.Thread(target=self._read_loop, daemon=True).start()
        self._initialize()

    def _read_loop(self):
        while self._alive:
            line = self.proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            slot = self._pending.get(msg.get("id"))
            if slot is not None:
                slot["error"] = msg.get("error")
                slot["result"] = msg.get("result", {})
                slot["event"].set()

    def _write(self, msg):
        with self._write_lock:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()

    def _request(self, method, params=None, timeout=20):
        with self._id_lock:
            self._id += 1
            rid = self._id
        ev = threading.Event()
        self._pending[rid] = {"event": ev, "result": None, "error": None}
        self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        if not ev.wait(timeout):
            self._pending.pop(rid, None)
            raise TimeoutError(f"MCP {method} timed out")
        slot = self._pending.pop(rid)
        if slot["error"]:
            raise RuntimeError(slot["error"])
        return slot["result"] or {}

    def _notify(self, method, params=None):
        self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _initialize(self):
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "agent-core", "version": "0.1"},
        })
        self._notify("notifications/initialized")

    def list_tools(self):
        return self._request("tools/list").get("tools", [])

    def call(self, tool, arguments):
        res = self._request("tools/call", {"name": tool, "arguments": arguments or {}})
        parts = []
        for c in res.get("content", []):
            parts.append(c.get("text", "") if c.get("type") == "text" else json.dumps(c))
        text = "\n".join(p for p in parts if p) or json.dumps(res)
        if res.get("isError"):
            return "ERROR: " + text
        return _wrap_untrusted(text, "mcp_output", server=self.name, tool=tool)


def mcp_call(server: str, tool: str, arguments: dict = None) -> str:
    client = _clients.get(server)
    if not client:
        return (f"MCP tool unavailable: no connected server named {server!r} (configure it in "
                "config/mcp.yaml). Don't surface this as your answer — proceed without it, or tell "
                "the user this connector isn't set up.")
    try:
        return client.call(tool, arguments or {})
    except Exception as e:
        return f"ERROR calling {server}.{tool}: {type(e).__name__}: {e}"


def _register_server(srv: dict):
    name = srv.get("name")
    if not name or not srv.get("command"):
        return
    try:
        client = MCPClient(name, srv["command"], srv.get("args", []))
        tools = client.list_tools()
    except Exception as e:
        print(f"[mcp] server {name!r} unavailable: {type(e).__name__}: {e}")
        return
    _clients[name] = client
    # Fail SAFE: an external connector's capabilities are unknown, so default to the
    # most-restrictive gate (critical + human approval). Loosen explicitly per server
    # in config/mcp.yaml once you trust it.
    risk = _RISK.get(srv.get("risk", "critical"), toolbelt.RISK_CRITICAL)
    requires_human = bool(srv.get("requires_human", True))
    granted = []
    for t in tools:
        full = f"mcp__{name}__{t['name']}"
        schema = t.get("inputSchema") or {"type": "object", "properties": {}}

        def _make(cn=name, tn=t["name"]):
            return lambda **kw: _clients[cn].call(tn, kw)

        toolbelt.register_fn(full, _make(), schema, t.get("description", ""),
                             risk, requires_human)
        granted.append(full)

    # Least privilege: grant these tools only to the agents listed for this server.
    for aid in srv.get("agents", []):
        ag = agent_registry.get(aid)
        if ag:
            ag.tools = list(ag.tools) + granted
    print(f"[mcp] connected {name!r}: {len(granted)} tools -> {srv.get('agents', [])}")


def register_configured_servers():
    if not os.path.exists(_CONFIG):
        return
    try:
        cfg = yaml.safe_load(open(_CONFIG, encoding="utf-8")) or {}
    except Exception as e:
        print(f"[mcp] could not read {_CONFIG}: {e}")
        return
    for srv in cfg.get("servers", []):
        _register_server(srv)


# A generic entry point so an agent can call any connected server explicitly.
toolbelt.register_fn(
    "mcp_call", mcp_call,
    {"type": "object",
     "properties": {"server": {"type": "string"}, "tool": {"type": "string"},
                    "arguments": {"type": "object"}},
     "required": ["server", "tool"]},
    "Call a tool on a connected MCP server.", toolbelt.RISK_CRITICAL, requires_human=True,
)

register_configured_servers()
