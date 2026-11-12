# Offline dry run of the composite action's steps.
# Usage: pwsh -File scripts/demo_ci.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$workdir = Join-Path $root "examples/consumer"
$report = Join-Path $root "reports/ci.json"
$html = Join-Path $root "reports/ci.html"
$baseline = Join-Path $workdir ".evalgate/baseline.json"
$comment = Join-Path $root "reports/ci-comment.md"

Write-Host "== validate =="
uv run evalgate validate (Join-Path $workdir "suite.yaml")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== baseline =="
if (-not (Test-Path $baseline)) {
    Write-Host "No baseline at $baseline; run without one"
    $baselineArg = @()
} else {
    Write-Host "Using baseline $baseline"
    $baselineArg = @("--baseline", $baseline)
}

Write-Host "== run =="
uv run evalgate run (Join-Path $workdir "suite.yaml") --mock `
    --json $report --html $html @baselineArg
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host "run exited $code (expected 0 for the committed baseline)" -ForegroundColor Yellow
}

Write-Host "== render comment =="
uv run evalgate comment --report $report --baseline $baseline --output $comment
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== artifacts =="
Get-Item $report, $html, $comment | Select-Object FullName, Length
Write-Host "DRY RUN COMPLETE (exit $code)"
exit $code
