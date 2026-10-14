# Runs the FastAPI backend (port 8000) and the Vite dashboard (port 5173) together.
# Usage:  .\scripts\dev.ps1        Stop with Ctrl+C (stops both).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dashboard = Join-Path $root 'dashboard'

Write-Host '==> Syncing Python deps (uv sync)' -ForegroundColor Yellow
Push-Location $root
try { uv sync; if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' } } finally { Pop-Location }

if (-not (Test-Path (Join-Path $dashboard 'node_modules'))) {
    Write-Host '==> Installing dashboard deps (npm install)' -ForegroundColor Yellow
    Push-Location $dashboard
    try { npm install; if ($LASTEXITCODE -ne 0) { throw 'npm install failed' } } finally { Pop-Location }
}

Write-Host '==> Starting backend on http://localhost:8000' -ForegroundColor Yellow
$backend = Start-Process -FilePath 'uv' -WorkingDirectory $root -NoNewWindow -PassThru `
    -ArgumentList 'run', 'uvicorn', 'backend.api.main:app', '--reload', '--port', '8000'

try {
    Write-Host '==> Starting dashboard on http://localhost:5173  (Ctrl+C stops both)' -ForegroundColor Yellow
    Push-Location $dashboard
    npm run dev
}
finally {
    Pop-Location
    if ($backend -and -not $backend.HasExited) {
        Write-Host '==> Stopping backend' -ForegroundColor Yellow
        # /T also stops the uvicorn reloader's child processes.
        taskkill /PID $backend.Id /T /F | Out-Null
    }
}
