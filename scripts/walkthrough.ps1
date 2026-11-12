# End-to-end walkthrough from docs/plan.md section 9. Offline except the compose step.
# Usage: pwsh -File scripts/walkthrough.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Path reports -Force | Out-Null

function Assert-Code {
    param([string]$Label, [int]$Actual, [int]$Expected)
    if ($Actual -ne $Expected) {
        Write-Host "FAILED: $Label (exit $Actual, expected $Expected)" -ForegroundColor Red
        exit 1
    }
    Write-Host "ok: $Label (exit $Actual)" -ForegroundColor Green
}

Write-Host "== 1. validate =="
uv run evalgate validate examples/support/suite.yaml
Assert-Code "validate" $LASTEXITCODE 0

Write-Host "== 2. baseline run with artifacts =="
uv run evalgate run examples/support/suite.yaml --mock --no-cache `
    --json reports/w1.json --html reports/w1.html
Assert-Code "baseline run" $LASTEXITCODE 0
if (-not (Test-Path reports/w1.json) -or -not (Test-Path reports/w1.html)) {
    Write-Host "FAILED: artifacts missing" -ForegroundColor Red
    exit 1
}

Write-Host "== 3. warm run uses the judge cache =="
Remove-Item -Recurse -Force .evalgate-cache -ErrorAction SilentlyContinue
uv run evalgate run examples/support/suite.yaml --mock --json reports/w0.json
Assert-Code "cold run" $LASTEXITCODE 0
uv run evalgate run examples/support/suite.yaml --mock --json reports/w2.json
Assert-Code "warm run" $LASTEXITCODE 0
$warm = Get-Content reports/w2.json -Raw | ConvertFrom-Json
if ($warm.summary.judge_cache_hits -ne 40 -or $warm.summary.judge_calls -ne 0) {
    Write-Host "FAILED: expected 0 calls / 40 hits, got $($warm.summary.judge_calls) / $($warm.summary.judge_cache_hits)" -ForegroundColor Red
    exit 1
}
Write-Host "ok: cache 0 calls / 40 hits" -ForegroundColor Green

Write-Host "== 4. weakened prompt is a regression =="
uv run evalgate run examples/support/suite.yaml --mock --prompt-variant weakened `
    --baseline reports/w1.json --json reports/w3.json
Assert-Code "weakened run" $LASTEXITCODE 1
$weak = Get-Content reports/w3.json -Raw | ConvertFrom-Json
if (-not $weak.baseline.regression.is_regression) {
    Write-Host "FAILED: regression not detected" -ForegroundColor Red
    exit 1
}
Write-Host "ok: regression detected with $($weak.summary.passed)/$($weak.summary.total) passing" -ForegroundColor Green

Write-Host "== 5. hard limit fails independently =="
$limitDir = "reports/w-limit"
New-Item -ItemType Directory -Path $limitDir -Force | Out-Null
Set-Content -Path "$limitDir/prompt.md" -Value "{{ input }}"
Set-Content -Path "$limitDir/cases.jsonl" -Value '{"id":"a","input":"hi","expected":"ok"}'
@"
name: hard-limit-demo
model:
  provider: mock
  name: mock
prompt: prompt.md
cases_file: cases.jsonl
metrics:
  - type: exact_match
limits:
  max_p95_latency_ms: 10
"@ | Set-Content -Path "$limitDir/suite.yaml"
uv run evalgate run "$limitDir/suite.yaml" --mock --mock-latency-ms 50
Assert-Code "hard limit" $LASTEXITCODE 1

Write-Host "== 6. calibration =="
uv run evalgate calibrate --suite examples/support/suite.yaml --mock --cases 10 `
    --output reports/w-calibration.md
Assert-Code "calibrate" $LASTEXITCODE 0
if (-not (Test-Path reports/w-calibration.md)) {
    Write-Host "FAILED: calibration report missing" -ForegroundColor Red
    exit 1
}

Write-Host "== 7. compose API run =="
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit 1 }
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8001/healthz" -TimeoutSec 3
        if ($health.status -eq "ok") { $ready = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $ready) {
    Write-Host "FAILED: API did not become healthy" -ForegroundColor Red
    docker compose logs --tail 40 api
    docker compose down -v
    exit 1
}
$body = @{ suite = "examples/support/suite.yaml"; mock = $true } | ConvertTo-Json
$created = Invoke-RestMethod -Uri "http://localhost:8001/v1/runs" -Method Post `
    -Headers @{ "X-API-Key" = "dev-key" } -ContentType "application/json" -Body $body
$runId = $created.id
$status = $created.status
for ($i = 0; $i -lt 60; $i++) {
    $run = Invoke-RestMethod -Uri "http://localhost:8001/v1/runs/$runId" `
        -Headers @{ "X-API-Key" = "dev-key" }
    $status = $run.status
    if ($status -in @("passed", "failed", "error")) { break }
    Start-Sleep -Seconds 1
}
if ($status -ne "passed") {
    Write-Host "FAILED: API run status $status" -ForegroundColor Red
    docker compose down -v
    exit 1
}
Write-Host "ok: API run $runId passed" -ForegroundColor Green

Write-Host "== 8. unauthenticated request =="
$unauthCode = 0
try {
    Invoke-WebRequest -Uri "http://localhost:8001/v1/runs/$runId" -Method Get | Out-Null
} catch {
    $unauthCode = [int]$_.Exception.Response.StatusCode
}
if ($unauthCode -ne 401) {
    Write-Host "FAILED: expected 401, got $unauthCode" -ForegroundColor Red
    docker compose down -v
    exit 1
}
Write-Host "ok: 401 without X-API-Key" -ForegroundColor Green

Write-Host "== 9. actionlint =="
docker run --rm -v "${root}:/repo" -w /repo rhysd/actionlint:latest
Assert-Code "actionlint" $LASTEXITCODE 0

Write-Host "== 10. render PR comment for the weakened run =="
uv run evalgate comment --report reports/w3.json --baseline reports/w1.json `
    --output reports/w-comment.md
Assert-Code "comment" $LASTEXITCODE 0
$comment = Get-Content reports/w-comment.md -Raw
if ($comment -notmatch "evalgate:report") {
    Write-Host "FAILED: comment marker missing" -ForegroundColor Red
    docker compose down -v
    exit 1
}

Write-Host "== 11. judge failure paths =="
uv run pytest tests/unit/test_judges.py -q
Assert-Code "judge tests" $LASTEXITCODE 0

Write-Host "== 12. full offline test suite =="
uv run pytest -q
Assert-Code "pytest" $LASTEXITCODE 0

Write-Host "== 13. docker image =="
docker build -t evalgate:walkthrough .
Assert-Code "docker build" $LASTEXITCODE 0
docker run --rm evalgate:walkthrough evalgate --help | Out-Null
Assert-Code "docker run" $LASTEXITCODE 0

Write-Host "== cleanup =="
docker compose down -v
Write-Host "WALKTHROUGH PASSED" -ForegroundColor Green
