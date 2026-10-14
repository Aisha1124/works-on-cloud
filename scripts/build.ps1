# Builds the dashboard into dashboard\dist (served by FastAPI at /).
# Usage:  .\scripts\build.ps1
$ErrorActionPreference = 'Stop'
$dashboard = Join-Path (Split-Path -Parent $PSScriptRoot) 'dashboard'

Push-Location $dashboard
try {
    if (-not (Test-Path 'node_modules')) {
        Write-Host '==> Installing dashboard deps (npm ci)' -ForegroundColor Yellow
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
    }
    Write-Host '==> Type-checking and building dashboard' -ForegroundColor Yellow
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Dashboard build failed' }
    Write-Host "==> Built: $(Join-Path $dashboard 'dist')" -ForegroundColor Green
}
finally {
    Pop-Location
}
