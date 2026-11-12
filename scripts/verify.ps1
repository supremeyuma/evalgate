# Full phase gate for EvalGate. Fails on the first error.
# Usage: pwsh -File scripts/verify.ps1  (or .\scripts\verify.ps1)
$ErrorActionPreference = "Stop"

function Invoke-Step {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "== $Name =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $Name (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Invoke-Step "format" { uv run ruff format --check . }
Invoke-Step "lint" { uv run ruff check . }
Invoke-Step "typecheck" { uv run mypy }
Invoke-Step "tests" { uv run pytest --cov --cov-report=term-missing --cov-report=xml }

Write-Host "ALL CHECKS PASSED" -ForegroundColor Green
