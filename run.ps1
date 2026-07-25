# run.ps1 — start (or restart) the app on Windows. Simple and stable by default.
#
#   .\run.ps1            start the server — STABLE (never restarts itself; long agent
#                        runs like cloning/analysing a repo can't be interrupted).
#                        Run it again anytime to restart: it frees the port first.
#   .\run.ps1 -Reload    developer mode: auto-reload when you edit SOURCE code
#                        (watches server/core/tools only — never data/, so an agent
#                        writing files can't trip the reloader and kill a run).
#   .\run.ps1 -Dev       frontend hot-reload (Vite); start the server separately.
param([switch]$Dev, [switch]$Reload)

if ($Dev) {
  Write-Host "Starting Vite dev server (proxies API+WS to :8800). Start the server separately: .\run.ps1" -ForegroundColor Cyan
  npm --prefix web install
  npm --prefix web run dev
  return
}

# Make "start" also mean "restart": free port 8800 first, so there's never an orphaned
# server or an 'address already in use'. Kills the whole process tree (incl. MCP children).
$busy = (Get-NetTCPConnection -LocalPort 8800 -State Listen -ErrorAction SilentlyContinue).OwningProcess |
        Select-Object -Unique
foreach ($procId in $busy) {
  Write-Host "Stopping existing server on :8800 (PID $procId)..." -ForegroundColor DarkYellow
  taskkill /F /T /PID $procId 2>$null | Out-Null
  Start-Sleep -Milliseconds 600
}

if (-not (Test-Path "web/dist")) {
  Write-Host "Building frontend..." -ForegroundColor Cyan
  npm --prefix web install
  npm --prefix web run build
}

# Run uvicorn via the venv's python (-m), NOT uvicorn.exe: the .exe launchers bake in an
# absolute python path at venv-creation time, so they break if the repo is moved (C: -> D:).
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

if ($Reload) {
  # Dev auto-reload — but ONLY watch source dirs, NEVER data/. Watching the whole tree (the
  # old default) meant the agent writing into data/workspaces (a clone, a multi-file build)
  # tripped the reloader and restarted the server mid-run -> "connection closed before it
  # finished". Scoping to source means only YOUR code edits trigger a reload.
  Write-Host "Starting server (auto-reload on source edits) at http://localhost:8800" -ForegroundColor Green
  & $py -m uvicorn server.app:app --reload --reload-dir server --reload-dir core --reload-dir tools --port 8800
} else {
  # Default: a stable server. It never restarts itself, so nothing an agent does to its own
  # workspace can interrupt a run. To pick up code changes, just re-run .\run.ps1.
  Write-Host "Starting server at http://localhost:8800  (stable - re-run .\run.ps1 to restart)" -ForegroundColor Green
  & $py -m uvicorn server.app:app --port 8800
}
