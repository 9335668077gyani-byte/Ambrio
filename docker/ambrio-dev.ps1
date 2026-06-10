#!/usr/bin/env pwsh
# docker/ambrio-dev.ps1
# ─── One-command dev stack launcher ──────────────────────────────────────────
# Usage: .\docker\ambrio-dev.ps1 [up|down|logs|shell|test|pull-models]

param(
    [Parameter(Position=0)]
    [ValidateSet("up","down","logs","shell","test","pull-models","status","clean")]
    [string]$Action = "up"
)

$COMPOSE = "docker compose -f docker-compose.yml -f docker-compose.dev.yml"
$API_SVC  = "ambrio-api"

function Write-Header($msg) {
    Write-Host "`n═══ $msg ═══" -ForegroundColor Cyan
}

switch ($Action) {

    "up" {
        Write-Header "Starting Ambrio DEV stack"
        # Copy env template if .env missing
        if (-not (Test-Path ".env")) {
            Copy-Item ".env.docker" ".env"
            Write-Host "⚠  Created .env from .env.docker — fill in your API keys!" -ForegroundColor Yellow
        }
        Invoke-Expression "$COMPOSE up --build -d"
        Write-Host "`n✅ Stack running:" -ForegroundColor Green
        Write-Host "   API:      ws://localhost:8765/chat/{session_id}" -ForegroundColor White
        Write-Host "   ChromaDB: http://localhost:8001/api/v1/collections" -ForegroundColor White
        Write-Host "   Ollama:   http://localhost:11434/api/tags" -ForegroundColor White
        Write-Host "`n   Run '.\docker\ambrio-dev.ps1 logs' to follow logs" -ForegroundColor DarkGray
    }

    "down" {
        Write-Header "Stopping Ambrio DEV stack"
        Invoke-Expression "$COMPOSE down"
    }

    "logs" {
        Write-Header "Following logs ($API_SVC)"
        Invoke-Expression "$COMPOSE logs -f $API_SVC"
    }

    "shell" {
        Write-Header "Opening shell in ambrio-api container"
        Invoke-Expression "$COMPOSE exec $API_SVC sh"
    }

    "test" {
        Write-Header "Running tests inside container"
        Invoke-Expression "$COMPOSE exec $API_SVC python -m pytest tests/unit/ -v --tb=short"
    }

    "pull-models" {
        Write-Header "Pulling Ollama models (phi3:mini + llama3.2)"
        Invoke-Expression "$COMPOSE exec ollama ollama pull phi3:mini"
        Invoke-Expression "$COMPOSE exec ollama ollama pull llama3.2"
        Write-Host "`n✅ Models ready" -ForegroundColor Green
    }

    "status" {
        Write-Header "Service health status"
        Invoke-Expression "$COMPOSE ps"
        Write-Host "`nChromaDB heartbeat:" -ForegroundColor DarkGray
        try { Invoke-WebRequest -Uri "http://localhost:8001/api/v1/heartbeat" -UseBasicParsing | Select-Object -ExpandProperty Content } catch { "  ✗ not reachable" }
        Write-Host "Ambrio API health:" -ForegroundColor DarkGray
        try { Invoke-WebRequest -Uri "http://localhost:8765/health"           -UseBasicParsing | Select-Object -ExpandProperty Content } catch { "  ✗ not reachable" }
    }

    "clean" {
        Write-Header "Removing containers + volumes (DATA WILL BE DELETED)"
        $confirm = Read-Host "Type 'yes' to confirm"
        if ($confirm -eq "yes") {
            Invoke-Expression "$COMPOSE down -v --remove-orphans"
            Write-Host "✅ Clean done" -ForegroundColor Green
        } else {
            Write-Host "Cancelled." -ForegroundColor Yellow
        }
    }
}
