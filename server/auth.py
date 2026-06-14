"""
auth.py — a minimal, safe-by-default authentication gate for the API + WebSocket.

Policy:
  * If AGENT_AUTH_TOKEN is set, EVERY /api request and WebSocket connection must
    present it (Authorization: Bearer <token>, or X-Auth-Token header, or ?token=
    query param for the WebSocket / EventSource where headers are awkward).
  * If AGENT_AUTH_TOKEN is NOT set, requests are allowed ONLY from loopback
    (127.0.0.1 / ::1). Anything reaching the server from another host is rejected
    with a clear message telling the operator to set AGENT_AUTH_TOKEN.

This means: localhost development needs no token, but the moment the app is
reachable over a network it refuses to serve the API until a token is configured —
so it can't be deployed wide-open by accident.
"""
import os
import hmac

from fastapi import Request, HTTPException, status

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _configured_token() -> str:
    return (os.environ.get("AGENT_AUTH_TOKEN") or "").strip()


# ---- email + password login (optional UI gate on top of the token) ----------
# When AGENT_LOGIN_EMAIL + AGENT_LOGIN_PASSWORD are set, the SPA shows a login
# screen and exchanges the credentials for the auth token via POST /api/login.
# If they are NOT set, the login screen is skipped (token/loopback rules apply).

def _login_creds() -> tuple[str, str]:
    return ((os.environ.get("AGENT_LOGIN_EMAIL") or "").strip(),
            (os.environ.get("AGENT_LOGIN_PASSWORD") or ""))


def login_enabled() -> bool:
    email, pw = _login_creds()
    return bool(email and pw)


def login_email() -> str:
    return _login_creds()[0]


def verify_login(email: str, password: str) -> bool:
    cfg_email, cfg_pw = _login_creds()
    if not (cfg_email and cfg_pw):
        return False
    ok_email = hmac.compare_digest((email or "").strip().lower(), cfg_email.lower())
    ok_pw = hmac.compare_digest(password or "", cfg_pw)
    return ok_email and ok_pw


def issued_token() -> str:
    """The token a client should use after a successful login: the real auth
    token when configured, else a harmless sentinel (loopback dev ignores it)."""
    return _configured_token() or "local-session"


def _present_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-auth-token")
            or request.query_params.get("token")
            or "").strip()


def _client_host(request: Request) -> str:
    return (request.client.host if request.client else "") or ""


def _check(token_present: str, client_host: str) -> tuple[bool, str]:
    """Pure decision: (allowed, reason). Shared by REST + WS."""
    configured = _configured_token()
    if configured:
        if token_present and hmac.compare_digest(token_present, configured):
            return True, "token ok"
        return False, "missing or invalid auth token"
    # No token configured -> only loopback is allowed.
    if client_host in _LOOPBACK:
        return True, "loopback (no token configured)"
    return False, ("server is reachable from the network but AGENT_AUTH_TOKEN is "
                   "not set — refusing to serve the API. Set AGENT_AUTH_TOKEN.")


async def require_auth(request: Request) -> None:
    """FastAPI dependency for REST routes."""
    allowed, reason = _check(_present_token(request), _client_host(request))
    if not allowed:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, reason)


def ws_authorized(websocket) -> tuple[bool, str]:
    """Authorize a WebSocket BEFORE accepting it. Reads the token from the
    Authorization/X-Auth-Token header or the ?token= query param."""
    headers = {k.decode().lower(): v.decode() for k, v in websocket.scope.get("headers", [])}
    auth = headers.get("authorization", "")
    token = (auth[7:].strip() if auth.lower().startswith("bearer ")
             else headers.get("x-auth-token", "")
             or websocket.query_params.get("token", "")).strip()
    client_host = (websocket.client.host if websocket.client else "") or ""
    return _check(token, client_host)
