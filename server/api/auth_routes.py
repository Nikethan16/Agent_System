"""
auth_routes.py — login endpoints for the optional email + password UI gate.

  GET  /api/auth/config  (public)  -> { login_enabled }
  POST /api/login        (public)  -> validate email+password, return the auth token
  GET  /api/me           (gated)   -> { email }  (also used to verify a stored token)

The actual API protection still lives in auth.py (token / loopback). Login is just
a friendlier way to obtain that token: enter the right email+password, get the token.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ..auth import login_enabled, login_email, verify_login, issued_token, require_auth

router = APIRouter(prefix="/api", tags=["auth"])


class LoginBody(BaseModel):
    email: str = ""
    password: str = ""


@router.get("/auth/config")
def auth_config():
    """Public: tells the SPA whether to show the login screen at all."""
    return {"login_enabled": login_enabled()}


@router.post("/login")
def login(body: LoginBody):
    """Public: exchange email+password for the auth token."""
    if not login_enabled():
        # Login isn't configured — nothing to gate; hand back a token so the UI proceeds.
        return {"token": issued_token(), "email": ""}
    if not verify_login(body.email, body.password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"token": issued_token(), "email": login_email()}


@router.get("/me", dependencies=[Depends(require_auth)])
def me():
    """Gated: returns the signed-in identity. A 401 here tells the SPA the stored
    token is missing/invalid, so it should show the login screen."""
    return {"email": login_email() or "local", "login_enabled": login_enabled()}
