"""Tests for Nikki's stdio MCP server — JSON-RPC dispatch, tool listing/calling, and the
headless safety defaults. handle_request is pure, so no real stdio is needed."""
from server import mcp_server as mcp


def _call(method, params=None, rid=1):
    return mcp.handle_request({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})


def test_initialize_handshake():
    r = _call("initialize")
    assert r["result"]["protocolVersion"] == mcp.PROTOCOL_VERSION
    assert r["result"]["serverInfo"]["name"] == "nikki"
    assert "tools" in r["result"]["capabilities"]


def test_initialized_notification_gets_no_reply():
    assert mcp.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_shape_and_no_handler_leak():
    tools = _call("tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"nikki_memory_search", "nikki_list_agents", "nikki_status",
            "nikki_fuse", "nikki_run_task"} <= names
    for t in tools:
        assert set(t.keys()) == {"name", "description", "inputSchema"}    # handler stripped
        assert t["inputSchema"]["type"] == "object"


def test_call_memory_search(monkeypatch):
    from server import memory
    monkeypatch.setattr(memory, "recall", lambda q, k=5: ["note one", "note two"])
    text = _call("tools/call", {"name": "nikki_memory_search",
                                "arguments": {"query": "x"}})["result"]["content"][0]["text"]
    assert "note one" in text and "note two" in text


def test_call_list_agents_reads_real_registry():
    text = _call("tools/call", {"name": "nikki_list_agents", "arguments": {}})["result"]["content"][0]["text"]
    assert "tier" in text.lower() and len(text) > 0


def test_call_unknown_tool_errors():
    assert _call("tools/call", {"name": "nope", "arguments": {}})["error"]["code"] == -32602


def test_call_bad_arguments_errors():
    r = _call("tools/call", {"name": "nikki_memory_search", "arguments": {"unexpected": 1}})
    assert r["error"]["code"] == -32602


def test_run_task_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_MCP_ALLOW_RUN", raising=False)
    text = _call("tools/call", {"name": "nikki_run_task",
                                "arguments": {"task": "do a thing"}})["result"]["content"][0]["text"]
    assert "disabled" in text.lower()


def test_unknown_method():
    assert _call("bogus/method")["error"]["code"] == -32601
    assert mcp.handle_request({"jsonrpc": "2.0", "method": "bogus"}) is None    # notification


def test_deny_risky_hook_denies():
    allowed, reason = mcp._deny_risky("run_bash", {"command": "rm -rf /"}, None)
    assert allowed is False and reason
