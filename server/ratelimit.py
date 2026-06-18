"""
ratelimit.py — lightweight in-process request throttling for the REST API.

Single-process deployment (one systemd service on the VM), so in-memory per-IP
state is sufficient — same pattern as core/llm.py's circuit breaker. Needed
before the API is reachable from the open internet (was previously deferred
since the app was Tailscale-only — see HANDOFF.md backlog).

Two independent limiters, both fail OPEN on misconfiguration (0/negative env
value disables them) so a bug here can never lock out legitimate use:
  * a general per-IP request cap on every /api/* call
  * a stricter login-attempt lockout (brute-force protection on /api/login)
"""
import os
import time
import threading

_lock = threading.Lock()


def client_ip(request) -> str:
    """Best-effort client IP: honors X-Forwarded-For (set by a reverse proxy such
    as `tailscale serve`/Funnel) before falling back to the direct socket peer.
    Used only for rate-limiting (best-effort, fail-open) — never for auth decisions,
    so a spoofed header can at most reset an attacker's own bucket."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return (request.client.host if request.client else "") or ""

# ---- general per-IP request rate limit --------------------------------------
_PER_MIN = int(os.environ.get("AGENT_RATE_LIMIT_PER_MIN", "120"))
_WINDOW = 60.0
_buckets: dict[str, list[float]] = {}  # ip -> recent request timestamps (sliding window)


def allow_request(client_ip: str) -> bool:
    """Sliding-window check: True if `client_ip` is under the per-minute cap."""
    if _PER_MIN <= 0:
        return True
    now = time.time()
    with _lock:
        ts = _buckets.setdefault(client_ip, [])
        cutoff = now - _WINDOW
        i = 0
        while i < len(ts) and ts[i] < cutoff:
            i += 1
        if i:
            del ts[:i]
        if len(ts) >= _PER_MIN:
            return False
        ts.append(now)
        return True


# ---- login brute-force lockout ----------------------------------------------
_MAX_ATTEMPTS = int(os.environ.get("AGENT_LOGIN_MAX_ATTEMPTS", "5"))
_LOCKOUT_SECONDS = float(os.environ.get("AGENT_LOGIN_LOCKOUT_SECONDS", "60"))
_failures: dict[str, list[float]] = {}   # ip -> recent failure timestamps
_locked_until: dict[str, float] = {}     # ip -> epoch until which it's locked


def login_locked(client_ip: str) -> float:
    """Seconds remaining until `client_ip` may attempt login again (0 if not locked)."""
    if _MAX_ATTEMPTS <= 0:
        return 0.0
    with _lock:
        remaining = _locked_until.get(client_ip, 0.0) - time.time()
        return remaining if remaining > 0 else 0.0


def record_login_failure(client_ip: str) -> None:
    if _MAX_ATTEMPTS <= 0:
        return
    now = time.time()
    with _lock:
        ts = _failures.setdefault(client_ip, [])
        ts.append(now)
        cutoff = now - _LOCKOUT_SECONDS
        ts[:] = [t for t in ts if t >= cutoff]
        if len(ts) >= _MAX_ATTEMPTS:
            _locked_until[client_ip] = now + _LOCKOUT_SECONDS
            ts.clear()


def record_login_success(client_ip: str) -> None:
    with _lock:
        _failures.pop(client_ip, None)
        _locked_until.pop(client_ip, None)
