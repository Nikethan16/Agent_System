"""
mcp_http.py — HTTP transport for Nikki's MCP server.

POST /api/mcp with a JSON-RPC 2.0 body → the JSON-RPC response, using the SAME tool dispatch as
the stdio server (server.mcp_server.handle_request). This lets Claude Code / Cursor reach Nikki's
tools remotely over Tailscale, gated by AGENT_AUTH_TOKEN through the standard /api auth
(Authorization: Bearer <token>, mounted with require_auth in server/app.py).

A minimal, STATELESS Streamable-HTTP transport: synchronous request → JSON response (no SSE, no
session id) — enough for Nikki's synchronous tools. The blocking dispatch runs in a threadpool so
a slow tool (fuse / run_task) can't stall the event loop. Full SSE streaming + session management
are a follow-up if a client needs server-initiated messages.
"""
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool

from server.mcp_server import handle_request

router = APIRouter()

_PARSE_ERR = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
_INVALID = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}


@router.post("/api/mcp")
async def mcp_http(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_PARSE_ERR, status_code=400)

    if isinstance(body, list):                       # JSON-RPC batch
        results = []
        for msg in body:
            if isinstance(msg, dict):
                r = await run_in_threadpool(handle_request, msg)
                if r is not None:
                    results.append(r)
        return JSONResponse(results)

    if not isinstance(body, dict):
        return JSONResponse(_INVALID, status_code=400)

    resp = await run_in_threadpool(handle_request, body)
    if resp is None:                                 # a notification → no content
        return Response(status_code=202)
    return JSONResponse(resp)
