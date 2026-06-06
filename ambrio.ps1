# ambrio.ps1 — Ambrio Desktop Phase 3 Launcher
# Starts the Cognitive Router process then the UI process.
# Ctrl+C or closing the window terminates both.

param(
    [string]$DbPath = "ambrio.db",
    [switch]$NoRouter   # Skip router startup (if already running)
)

$Root   = $PSScriptRoot
$Python = "$Root\.venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "[ERROR] Virtual environment not found. Run: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

$RouterPid = $null

if (-not $NoRouter) {
    Write-Host ""
    Write-Host "  ⚡ Ambrio Desktop — Phase 3" -ForegroundColor Cyan
    Write-Host "  ──────────────────────────────" -ForegroundColor DarkGray
    Write-Host "  Starting Cognitive Router..." -ForegroundColor Yellow

    $RouterJob = Start-Process $Python `
        -ArgumentList "router_service.py" `
        -WorkingDirectory $Root `
        -PassThru `
        -WindowStyle Hidden

    $RouterPid = $RouterJob.Id
    Write-Host "  Router PID: $RouterPid" -ForegroundColor DarkGray

    # Wait for router to bind to ZMQ socket
    Start-Sleep -Milliseconds 1500
    Write-Host "  Router ready." -ForegroundColor Green
}

Write-Host "  Launching UI..." -ForegroundColor Cyan
Write-Host ""

try {
    & $Python app.py
} finally {
    if ($RouterPid) {
        Write-Host ""
        Write-Host "  Shutting down router (PID $RouterPid)..." -ForegroundColor Yellow
        Stop-Process -Id $RouterPid -ErrorAction SilentlyContinue
        Write-Host "  Done." -ForegroundColor Green
    }
}
