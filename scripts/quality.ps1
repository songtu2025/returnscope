param(
    [ValidateSet("check", "audit")]
    [string]$Mode = "check"
)

$ErrorActionPreference = "Stop"

python "$PSScriptRoot\quality.py" $Mode
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
