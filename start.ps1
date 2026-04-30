<#
.SYNOPSIS
    Start the PO to E-Invoice converter.

.PARAMETER Docker
    Run via Docker Compose instead of local Python.

.EXAMPLE
    .\start.ps1           # local dev
    .\start.ps1 -Docker   # docker
#>
param(
    [switch]$Docker
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "PO Converter"

function Write-Step($msg) { Write-Host "`n$msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "  FAIL  $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   PO to E-Invoice Converter" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ── Load .env ─────────────────────────────────────────────────────────────
Write-Step "Checking configuration..."

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Warning ".env created from .env.example"
        Write-Warning "Fill in OPENAI_API_KEY in .env, then re-run."
        exit 1
    }
    Write-Fail ".env not found and no .env.example to copy from"
}

foreach ($line in Get-Content ".env") {
    if ($line -match "^\s*([^#\s][^=]*)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
    }
}

# ── Validate required env vars ─────────────────────────────────────────────
if (-not $env:OPENAI_API_KEY)  { Write-Fail "OPENAI_API_KEY is not set in .env" }
Write-Ok "OPENAI_API_KEY is set"

if (-not $env:SMTP_HOST)       { Write-Fail "SMTP_HOST is not set in .env" }
if (-not $env:SMTP_USER)       { Write-Fail "SMTP_USER is not set in .env" }
if (-not $env:SMTP_PASSWORD)   { Write-Fail "SMTP_PASSWORD is not set in .env" }
Write-Ok "SMTP: $env:SMTP_USER via $env:SMTP_HOST"

$templatePath = if ($env:TEMPLATE_PATH) { $env:TEMPLATE_PATH } else { "templates\Finance_XLSX_Templates_new_new.xlsx" }
if (-not (Test-Path $templatePath)) {
    Write-Fail "Template not found: $templatePath`n  Place your XLSX template in the templates\ folder."
}
Write-Ok "Template: $templatePath"

# ══════════════════════════════════════════════════════════════════════════
if ($Docker) {
# ── DOCKER MODE ───────────────────────────────────────────────────────────

    Write-Step "Checking Docker..."
    try {
        docker info | Out-Null
        Write-Ok "Docker is running"
    } catch {
        Write-Fail "Docker is not running — start Docker Desktop and try again"
    }

    Write-Step "Building and starting containers (this may take a few minutes on first run)..."
    docker compose up --build

} else {
# ── LOCAL MODE ────────────────────────────────────────────────────────────

    Write-Step "Checking Python..."
    try {
        $pyVersion = python --version 2>&1
        Write-Ok $pyVersion
    } catch {
        Write-Fail "Python not found — install Python 3.11+ and add it to PATH"
    }

    # Prefer .venv if present, otherwise fall back to the system python
    $pythonExe = if (Test-Path ".venv\Scripts\python.exe") {
        ".venv\Scripts\python.exe"
    } else {
        "python"
    }
    Write-Ok "Python: $pythonExe"

    Write-Step "Installing dependencies..."
    & $pythonExe -m pip install -r requirements.txt -q
    if ($LASTEXITCODE -ne 0) { Write-Fail "pip install failed" }
    Write-Ok "Dependencies up to date"

    # ── Start backend in a new window ──────────────────────────────────────
    Write-Step "Starting backend on http://localhost:8000 ..."

    $backendCmd = "uvicorn main:app --port 8000 --reload"
    $backend = Start-Process powershell `
        -ArgumentList "-NoProfile -Command `"$backendCmd`"" `
        -PassThru

    # Poll /health until ready or 60s timeout
    $deadline = (Get-Date).AddSeconds(60)
    $ready    = $false
    Write-Host "  Waiting for backend to initialise..." -ForegroundColor DarkGray

    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        try {
            $r = Invoke-RestMethod "http://localhost:8000/health" -ErrorAction Stop
            if ($r.ready -eq $true) { $ready = $true; break }
        } catch {}
    }

    if (-not $ready) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
        Write-Fail "Backend did not become ready within 60s — check the backend window for errors"
    }
    Write-Ok "Backend ready  →  http://localhost:8000/docs"

    # ── Start Streamlit (foreground — Ctrl+C stops everything) ─────────────
    Write-Step "Starting frontend on http://localhost:8501 ..."
    Write-Host "  Press Ctrl+C to stop both services.`n" -ForegroundColor Yellow

    try {
        streamlit run frontend/app.py
    } finally {
        Write-Host "`nStopping backend..." -ForegroundColor Yellow
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
        Write-Host "Done." -ForegroundColor Green
    }
}
