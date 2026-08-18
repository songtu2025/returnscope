$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $projectRoot "web-prototype")
try {
    npm run build
}
finally {
    Pop-Location
}

Push-Location $projectRoot
try {
    python -m uvicorn web_backend.app:app --host 127.0.0.1 --port 8000
}
finally {
    Pop-Location
}
