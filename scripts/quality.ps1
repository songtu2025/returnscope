$ErrorActionPreference = "Stop"

python -m ruff check web_backend return_semantics return_analysis tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m ruff format --check web_backend return_semantics return_analysis tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m pytest tests -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location web-prototype
try {
    npm run quality
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
