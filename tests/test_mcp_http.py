"""HTTP transport for the MCP server (POST /api/mcp). Mounted on a minimal app with the real
auth dependency so we exercise the Bearer-token gate + JSON-RPC framing without booting the app."""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from server.api import mcp_http
from server.auth import require_auth

TOKEN = "test-token-abc123"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("AGENT_AUTH_TOKEN", TOKEN)      # force the token path (not loopback)
    app = FastAPI()
    app.include_router(mcp_http.router, dependencies=[Depends(require_auth)])
    return TestClient(app)


def _post(client, body, token=TOKEN):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/mcp", json=body, headers=headers)


def test_requires_auth_token(client):
    r = _post(client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token=None)
    assert r.status_code == 401


def test_initialize_over_http(client):
    r = _post(client, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert r.status_code == 200
    assert r.json()["result"]["serverInfo"]["name"] == "nikki"


def test_tools_list_over_http(client):
    r = _post(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert {"nikki_fuse", "nikki_status", "nikki_memory_search"} <= names


def test_tools_call_over_http(client, monkeypatch):
    from server import memory
    monkeypatch.setattr(memory, "recall", lambda q, k=5: ["a remembered note"])
    r = _post(client, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "nikki_memory_search", "arguments": {"query": "x"}}})
    assert "a remembered note" in r.json()["result"]["content"][0]["text"]


def test_notification_returns_202(client):
    r = _post(client, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert r.status_code == 202


def test_batch_request(client):
    r = _post(client, [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                       {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
    data = r.json()
    assert isinstance(data, list) and len(data) == 2


def test_parse_error(client):
    r = client.post("/api/mcp", content="not json at all",
                    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == -32700
