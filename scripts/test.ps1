# Runs the Python tests. Extra arguments go to pytest.
# Usage:  .\scripts\test.ps1            all tests
#         .\scripts\test.ps1 -k store   only matching tests
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    uv run pytest @args
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $code
