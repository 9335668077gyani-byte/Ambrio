# start_ambrio.ps1
# Ambrio Desktop -- Full launcher with preflight checks
# Usage:
#   .\start_ambrio.ps1              # normal start
#   .\start_ambrio.ps1 -NoRouter    # skip router (if already running)
#   .\start_ambrio.ps1 -Test        # run smoke test only, no UI

param(
    [string]$DbPath   = "ambrio.db",
    [switch]$NoRouter,
    [switch]$Test
)

$Root   = $PSScriptRoot
$Python = "$Root\.venv\Scripts\python.exe"
$Env:PYTHONPATH = $Root

Write-Host ""
Write-Host "  +-------------------------------------+" -ForegroundColor Magenta
Write-Host "  |   AMBRIO Desktop -- Local AI ERP   |" -ForegroundColor Magenta
Write-Host "  |   Powered by Ollama + PyQt6         |" -ForegroundColor DarkCyan
Write-Host "  +-------------------------------------+" -ForegroundColor Magenta
Write-Host ""

# ── Preflight checks ────────────────────────────────────────────────────────
$ok = $true

# Python venv
if (-not (Test-Path $Python)) {
    Write-Host "  [x] venv not found -- run: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Red
    $ok = $false
} else {
    Write-Host "  [ok] Python venv: $Python" -ForegroundColor Green
}

# Ollama check via CLI (more reliable than HTTP in all environments)
$ollamaOk = $false
if (-not (Get-Command "ollama" -ErrorAction SilentlyContinue)) {
    Write-Host "  [x] Ollama not found. Download from: https://ollama.com/download" -ForegroundColor Red
    $ok = $false
} else {
    try {
        $ollamaOut = & ollama list 2>&1
        $modelLine = $ollamaOut | Where-Object { $_ -match "\S" } | Select-Object -Skip 1 -First 1
        if ($modelLine) {
            $modelName = ($modelLine -split "\s+")[0]
            Write-Host "  [ok] Ollama ready -- model: $modelName" -ForegroundColor Green
        } else {
            Write-Host "  [!] Ollama found but no models installed. Run: ollama pull llama3.2:1b" -ForegroundColor Yellow
        }
        $ollamaOk = $true
    } catch {
        Write-Host "  [!] Ollama not running -- starting it..." -ForegroundColor Yellow
        Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
        Write-Host "  [ok] Ollama started (background)" -ForegroundColor Green
        $ollamaOk = $true
    }
}

# SparePartsPro DB
$spDbPath = "$env:APPDATA\SparePartsPro\spare_parts.db"
if (Test-Path $spDbPath) {
    Write-Host "  [ok] SparePartsPro DB: $spDbPath" -ForegroundColor Green
} else {
    Write-Host "  [~] SparePartsPro DB not found (ERP queries will be disabled)" -ForegroundColor DarkYellow
}

if (-not $ok) {
    Write-Host ""
    Write-Host "  [!] Fix the errors above before running Ambrio." -ForegroundColor Red
    exit 1
}

# ── Test-only mode ──────────────────────────────────────────────────────────
if ($Test) {
    Write-Host ""
    Write-Host "  Running smoke test..." -ForegroundColor Cyan
    & $Python -X utf8 tests/smoke_test.py
    exit $LASTEXITCODE
}

# ── Launch Router ────────────────────────────────────────────────────────────
$RouterPid = $null
if (-not $NoRouter) {
    Write-Host ""
    Write-Host "  Starting Cognitive Router..." -ForegroundColor Yellow
    $RouterJob = Start-Process $Python `
        -ArgumentList "router_service.py", "--db", $DbPath `
        -WorkingDirectory $Root `
        -PassThru `
        -WindowStyle Hidden
    $RouterPid = $RouterJob.Id
    Write-Host "  Router PID: $RouterPid -- ZMQ on tcp://127.0.0.1:5555" -ForegroundColor DarkGray
    Start-Sleep -Milliseconds 1500
    Write-Host "  [ok] Router ready" -ForegroundColor Green
}

# ── Launch UI ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Launching Ambrio UI..." -ForegroundColor Cyan
Write-Host ""

try {
    & $Python app.py
} finally {
    if ($RouterPid) {
        Write-Host ""
        Write-Host "  Shutting down Router (PID $RouterPid)..." -ForegroundColor Yellow
        Stop-Process -Id $RouterPid -ErrorAction SilentlyContinue
        Write-Host "  [ok] Shutdown complete." -ForegroundColor Green
    }
}
