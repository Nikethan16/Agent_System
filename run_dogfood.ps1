# run_dogfood.ps1 — one-command local self-engineering test.
#
#   .\run_dogfood.ps1                                  # built-in calc demo
#   .\run_dogfood.ps1 -SeedOnly                        # prepare only, no model calls
#   .\run_dogfood.ps1 -Dir .\myproject -Task "add a /health endpoint + a test"
#   .\run_dogfood.ps1 -Force                           # skip the model pre-check
#
# Uses the repo's venv python so the C:\ -> D:\ path move doesn't bite.
param(
  [string]$Dir,
  [string]$Task,
  [switch]$SeedOnly,
  [switch]$InPlace,
  [switch]$Force,
  [double]$MaxUsd = 1.0,
  [int]$MaxIter = 24
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  Write-Host "No venv python at $py — create it first:" -ForegroundColor Yellow
  Write-Host "  python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
  exit 1
}
if (-not (Test-Path (Join-Path $PSScriptRoot ".env"))) {
  Write-Host "Warning: no .env in the repo root — model keys won't load." -ForegroundColor Yellow
}

$cmd = @("-m", "scripts.dogfood", "--max-usd", $MaxUsd, "--max-iter", $MaxIter)
if ($Dir)      { $cmd += @("--dir", $Dir) }
if ($Task)     { $cmd += @("--task", $Task) }
if ($SeedOnly) { $cmd += "--seed-only" }
if ($InPlace)  { $cmd += "--in-place" }
if ($Force)    { $cmd += "--force" }

Write-Host "Running: $py $($cmd -join ' ')" -ForegroundColor Cyan
& $py @cmd
exit $LASTEXITCODE
