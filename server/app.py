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

from . import db, jobs, scheduler
from .auth import require_auth
from .api import sessions, workspace, models, ws
from .api import jobs as jobs_api
from .api import projects as projects_api
from .api import memory as memory_api
from .api import benchmark as benchmark_api
from .api import schedules as schedules_api

import tools  # noqa: F401  (registers web_search/web_fetch/generate_image/mcp_call)

app = FastAPI(title="Agent Core")

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
app.include_router(ws.router)

# Create tables at import so every entrypoint (uvicorn, TestClient, scripts) is ready.
db.init_db()


@app.on_event("startup")
def _resume_jobs():
    jobs.start_worker()        # resume any queued jobs after a restart
    scheduler.start_scheduler()  # start firing due scheduled tasks


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
