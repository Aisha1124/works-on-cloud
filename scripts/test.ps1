# Runs the Python tests, then (with no arguments) the dashboard tests. Extra arguments go to pytest.
# Usage:  .\scripts\test.ps1            all tests
#         .\scripts\test.ps1 -k store   only matching Python tests
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    uv run pytest @args
    $code = $LASTEXITCODE
    if ($code -eq 0 -and $args.Count -eq 0) {
        Push-Location (Join-Path $root 'dashboard')
        try { node ./node_modules/vitest/vitest.mjs run; $code = $LASTEXITCODE } finally { Pop-Location }
    }
}
finally {
    Pop-Location
}
exit $code
