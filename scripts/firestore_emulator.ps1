# Starts the local Firestore emulator (needs Java 11+ and Node; no gcloud, no Google account).
# Install Java once:  winget install EclipseAdoptium.Temurin.21.JRE
#
# Usage:  .\scripts\firestore_emulator.ps1          start it (Ctrl+C stops it)
# Then, in another PowerShell window:
#   $env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:8085"
#   uv run pytest tests/test_store.py               store tests on both backends
#   $env:STORE_BACKEND = "firestore"; $env:GCP_PROJECT_ID = "demo-kampungcart"
#   uv run uvicorn backend.api.main:app --port 8000  the app on the emulator
$root = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    Write-Host "Java is not installed. Run: winget install EclipseAdoptium.Temurin.21.JRE (then open a new window)." -ForegroundColor Red
    exit 1
}
Push-Location (Join-Path $root 'infra\firestore-emulator')
try {
    # "demo-" projects never touch a real Google Cloud project.
    npx --yes firebase-tools emulators:start --only firestore --project demo-kampungcart
}
finally {
    Pop-Location
}
