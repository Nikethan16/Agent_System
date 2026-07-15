# run.ps1 — build the frontend (if needed) and start the app on Windows.
#   .\run.ps1            normal run
#   .\run.ps1 -Dev       frontend hot-reload (also start uvicorn separately)
param([switch]$Dev)

if ($Dev) {
  Write-Host "Starting Vite dev server (proxies API+WS to :8800). Run uvicorn separately." -ForegroundColor Cyan
  npm --prefix web install
  npm --prefix web run dev
  return
}

if (-not (Test-Path "web/dist")) {
  Write-Host "Building frontend..." -ForegroundColor Cyan
  npm --prefix web install
  npm --prefix web run build
}
# Run uvicorn via the venv's python (-m), NOT uvicorn.exe: the .exe launchers bake in
# an absolute path to python at venv-creation time, so they break if the repo is moved
# (e.g. C:\ -> D:\). python.exe -m uvicorn is immune to that.
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
Write-Host "Starting server at http://localhost:8800" -ForegroundColor Green
& $py -m uvicorn server.app:app --reload --port 8800
