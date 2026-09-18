$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runtimeEnvironmentPath = Join-Path $projectRoot ".env.runtime.local"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "未找到项目 Python 环境：$pythonPath"
}

if (Test-Path -LiteralPath $runtimeEnvironmentPath) {
    $allowedVariables = @("WEBAPP_DATA_DIR", "WEBAPP_DATABASE_PATH")
    foreach ($line in Get-Content -LiteralPath $runtimeEnvironmentPath -Encoding utf8) {
        $entry = $line.Trim()
        if (-not $entry -or $entry.StartsWith("#")) {
            continue
        }
        $parts = $entry -split "=", 2
        if ($parts.Count -ne 2 -or $allowedVariables -notcontains $parts[0]) {
            throw "本地运行配置包含不支持的项目：$entry"
        }
        [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
    }
}

Push-Location (Join-Path $projectRoot "web-prototype")
try {
    npm run build
}
finally {
    Pop-Location
}

Push-Location $projectRoot
try {
    $databasePath = & $pythonPath -c "from web_backend.settings import Settings; print(Settings.from_env().database_path)"
    Write-Host "运行数据库：$databasePath"
    & $pythonPath -m uvicorn web_backend.app:app --host 0.0.0.0 --port 8000
}
finally {
    Pop-Location
}
