"""
mcp_example_server.py — a minimal MCP stdio server, for testing/demoing the adapter.

Implements the MCP handshake + two tools (echo, add) over newline-delimited JSON-RPC.
Real MCP servers (GitHub, Slack, databases, browsers, …) speak this same protocol;
point config/mcp.yaml at any of them the same way.
"""
import sys
import json

TOOLS = [
    {"name": "echo", "description": "Echo back the given text.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                     "required": ["text"]}},
    {"name": "add", "description": "Add two numbers and return the sum.",
     "inputSchema": {"type": "object",
                     "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                     "required": ["a", "b"]}},
]


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid, method = msg.get("id"), msg.get("method")

        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "example", "version": "0.1"},
            }})
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            p = msg.get("params", {})
            name, args = p.get("name"), p.get("arguments", {})
            if name == "echo":
                text = str(args.get("text", ""))
            elif name == "add":
                try:
                    text = str(float(args.get("a", 0)) + float(args.get("b", 0)))
                except Exception:
                    text = "ERROR: a and b must be numbers"
            else:
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": f"unknown tool {name}"}],
                    "isError": True}})
                continue
            send({"jsonrpc": "2.0", "id": mid,
                  "result": {"content": [{"type": "text", "text": text}]}})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid,
                  "error": {"code": -32601, "message": f"method not found: {method}"}})


if __name__ == "__main__":
    main()
