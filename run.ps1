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
# Prefer the project venv's uvicorn if it exists (no manual activation needed).
$uvicorn = if (Test-Path ".venv\Scripts\uvicorn.exe") { ".venv\Scripts\uvicorn.exe" } else { "uvicorn" }
Write-Host "Starting server at http://localhost:8800" -ForegroundColor Green
& $uvicorn server.app:app --reload --port 8800
