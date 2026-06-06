# Ambrio — Personal AI Assistant
# Launcher Script
# Run this once to set up and start Ambrio

Write-Host ""
Write-Host "  █████╗ ███╗   ███╗██████╗ ██████╗ ██╗ ██████╗ " -ForegroundColor Magenta
Write-Host " ██╔══██╗████╗ ████║██╔══██╗██╔══██╗██║██╔═══██╗" -ForegroundColor Magenta
Write-Host " ███████║██╔████╔██║██████╔╝██████╔╝██║██║   ██║" -ForegroundColor Magenta
Write-Host " ██╔══██║██║╚██╔╝██║██╔══██╗██╔══██╗██║██║   ██║" -ForegroundColor Magenta
Write-Host " ██║  ██║██║ ╚═╝ ██║██████╔╝██║  ██║██║╚██████╔╝" -ForegroundColor Magenta
Write-Host " ╚═╝  ╚═╝╚═╝     ╚═╝╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ " -ForegroundColor Magenta
Write-Host ""
Write-Host "  Your Personal Autonomous AI Assistant" -ForegroundColor Cyan
Write-Host "  Powered by Ollama · Runs 100% Locally" -ForegroundColor DarkCyan
Write-Host ""

# ── Check Python ───────────────────────────────────────────────────────────────
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "❌  Python not found. Please install Python 3.10+ and add to PATH." -ForegroundColor Red
    exit 1
}
Write-Host "✅  Python found." -ForegroundColor Green

# ── Check Ollama ───────────────────────────────────────────────────────────────
if (-not (Get-Command "ollama" -ErrorAction SilentlyContinue)) {
    Write-Host "❌  Ollama not found. Download from: https://ollama.com/download" -ForegroundColor Red
    exit 1
}
Write-Host "✅  Ollama found." -ForegroundColor Green

# ── Virtual Environment ────────────────────────────────────────────────────────
if (-not (Test-Path ".\.venv")) {
    Write-Host "⚙️   Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}
Write-Host "✅  Virtual environment ready." -ForegroundColor Green

# Activate
.\.venv\Scripts\Activate.ps1

# ── Install Dependencies ───────────────────────────────────────────────────────
Write-Host "📦  Installing dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
Write-Host "✅  Dependencies installed." -ForegroundColor Green

# ── Pull AI Model ──────────────────────────────────────────────────────────────
Write-Host "🧠  Pulling AI model (codegemma)..." -ForegroundColor Yellow
ollama pull codegemma
Write-Host "✅  Model ready." -ForegroundColor Green

# ── Launch Ambrio ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "🚀  Starting Ambrio..." -ForegroundColor Magenta
Write-Host "    Open your browser at: http://localhost:8501" -ForegroundColor Cyan
Write-Host ""
python -m streamlit run app.py --server.port 8501
