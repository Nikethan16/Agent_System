"""
app.py — the backend. Mounts the REST + WebSocket API and serves the React app.

Run:  uvicorn server.app:app --reload --port 8000
Then open http://localhost:8000

Importing `tools` activates the optional network capabilities (web/image/MCP) by
registering them into the tool registry. core itself stays offline.
"""
import os

from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, jobs, scheduler, ratelimit
from .auth import require_auth
from .api import sessions, workspace, models, ws
from .api import jobs as jobs_api
from .api import projects as projects_api
from .api import memory as memory_api
from .api import benchmark as benchmark_api
from .api import schedules as schedules_api
from .api import fleet as fleet_api
from .api import runs as runs_api
from .api import traces as traces_api
from .api import skills as skills_api
from .api import commands as commands_api
from .api import auth_routes

import tools  # noqa: F401  (registers web_search/web_fetch/generate_image/mcp_call)

app = FastAPI(title="Agent Core")


@app.middleware("http")
async def _rate_limit(request: Request, call_next):
    # General per-IP request cap on every /api/* call (server/ratelimit.py). Fails
    # open on misconfiguration; the WebSocket has its own connection-level auth and
    # isn't a repeatable-request vector the same way, so it's left uncapped here.
    if request.url.path.startswith("/api/"):
        ip = ratelimit.client_ip(request)
        if not ratelimit.allow_request(ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Slow down."},
                headers={"Retry-After": "60"},
            )
    return await call_next(request)


# Every REST router is gated by require_auth (loopback-only until AGENT_AUTH_TOKEN
# is set). The WebSocket is gated separately inside ws.py (it can't use Depends the
# same way). The SPA shell at "/" stays public — the API behind it is protected.
_auth = [Depends(require_auth)]
app.include_router(models.router, dependencies=_auth)
app.include_router(sessions.router, dependencies=_auth)
app.include_router(workspace.router, dependencies=_auth)
app.include_router(jobs_api.router, dependencies=_auth)
app.include_router(projects_api.router, dependencies=_auth)
app.include_router(memory_api.router, dependencies=_auth)
app.include_router(benchmark_api.router, dependencies=_auth)
app.include_router(schedules_api.router, dependencies=_auth)
app.include_router(fleet_api.router, dependencies=_auth)
app.include_router(runs_api.router, dependencies=_auth)
app.include_router(traces_api.router, dependencies=_auth)
app.include_router(skills_api.router, dependencies=_auth)
app.include_router(commands_api.router, dependencies=_auth)
# auth_routes defines its own per-route protection (/login + /auth/config are public,
# /me is gated), so it is NOT wrapped in the blanket _auth dependency.
app.include_router(auth_routes.router)
app.include_router(ws.router)

# Create tables at import so every entrypoint (uvicorn, TestClient, scripts) is ready.
db.init_db()


@app.on_event("startup")
def _resume_jobs():
    from . import runs
    runs.mark_stale_running_done()   # any run still "running" is orphaned from a prior process
    jobs.start_worker()          # resume any queued jobs after a restart
    scheduler.start_scheduler()  # start firing due scheduled tasks
    from . import auth
    auth.warn_if_weak_login()    # nudge: the app is internet-facing — flag a weak login pw
    _start_janitor()             # reclaim orphaned/aged traces+checkpoints (self-maintaining)
    # Wire the LLM observer so Langfuse gets generation spans (model/cost/tokens/latency).
    # core stays offline — it only holds a callback ref; no Langfuse import in core.
    from . import trace as _trace
    from core import llm as _llm
    _llm.register_llm_observer(_trace._llm_generation_callback)


def _start_janitor():
    """Best-effort disk hygiene so the 24/7 host self-maintains without a cron. Runs the
    SAFE sweep only (orphaned + aged traces/checkpoints — no workspaces, no docker) in a
    daemon thread so a slow disk can't delay startup. AGENT_DISABLE_JANITOR=1 turns it off."""
    if os.environ.get("AGENT_DISABLE_JANITOR", "").strip() in ("1", "true", "yes"):
        return
    import threading

    def _run():
        try:
            from scripts.cleanup import sweep
            days = int(os.environ.get("MAX_TRACE_AGE_DAYS", "30"))
            sweep(days=days, workspaces=False, docker=False)
        except Exception as e:      # never let hygiene break the server
            print(f"disk janitor skipped: {type(e).__name__}: {e}")

    threading.Thread(target=_run, name="disk-janitor", daemon=True).start()


@app.on_event("shutdown")
def _flush_traces():
    # Flush any buffered Langfuse spans so they aren't dropped on shutdown
    # (no-op when Langfuse isn't configured). Local JSONL traces are written eagerly.
    from . import trace
    trace.flush()


@app.exception_handler(db.InvalidId)
async def _invalid_id_handler(_request: Request, exc: db.InvalidId):
    # A crafted (non-UUID) id reached a filesystem join — reject as a bad request
    # rather than leaking a 500/stack trace.
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/spend", dependencies=_auth)
def spend_status():
    from . import spend
    return spend.status()


@app.get("/api/spend/overview", dependencies=_auth)
def spend_overview():
    """Cost dashboard feed: today vs cap, all-time total, a daily-spend series, and
    per-project spend (names + caps joined here, where the projects table lives)."""
    from . import spend, projects
    ov = spend.overview()
    plist = projects.list_all()
    names = {p["id"]: p.get("name", p["id"][:8]) for p in plist}
    caps = {p["id"]: float(p.get("budget_usd", 0.0) or 0.0) for p in plist}
    by_project = ov.pop("by_project", {})
    ov["projects"] = sorted(
        ({"project_id": pid, "name": names.get(pid, pid[:8]), "spent": usd,
          "cap": caps.get(pid) if caps.get(pid, 0) > 0 else None}
         for pid, usd in by_project.items()),
        key=lambda x: -x["spent"])[:12]
    return ov


# ---- serve the built React app (web/dist) if present ------------------------
_DIST = os.path.join(os.path.dirname(__file__), "..", "web", "dist")

if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")
else:
    @app.get("/")
    def _no_build():
        return HTMLResponse(
            "<h2>AGENT // CORE backend is running.</h2>"
            "<p>The frontend isn't built yet. In <code>web/</code> run "
            "<code>npm install &amp;&amp; npm run build</code> (or <code>npm run dev</code> "
            "for live development against this API).</p>",
            status_code=200,
        )
