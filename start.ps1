# ==============================================================================
# AI Legal Engine - Unified Full-Stack Startup Script
# ==============================================================================
# Usage:
#   .\start.ps1
#   npm run dev:all
# ==============================================================================

[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$Production
)

$WorkspaceRoot = $PSScriptRoot
if (-not $WorkspaceRoot) { $WorkspaceRoot = (Get-Location).Path }

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  AI LEGAL DECISION INTELLIGENCE ENGINE" -ForegroundColor White
Write-Host "  Starting Full Stack: Docker + Database + Backend + Frontend" -ForegroundColor DarkGray
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------------------------
# 1. Check Prerequisites & Python Environment
# ------------------------------------------------------------------------------
Write-Host "[1/5] Checking environment & runtimes..." -ForegroundColor Yellow

$PythonExe = Join-Path $WorkspaceRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = Join-Path $WorkspaceRoot "backend\venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonExe)) {
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCmd) {
        $PythonExe = $PythonCmd.Source
    } else {
        Write-Error "Python executable not found. Please ensure Python is installed and backend\.venv exists."
        exit 1
    }
}
Write-Host "  OK: Python runtime -> $PythonExe" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 2. Start Docker Containers (PostgreSQL & Neo4j)
# ------------------------------------------------------------------------------
Write-Host "`n[2/5] Starting Docker containers (PostgreSQL + Neo4j)..." -ForegroundColor Yellow
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        docker compose up -d db graph
        Write-Host "  OK: Docker containers active" -ForegroundColor Green
    } else {
        Write-Host "  Note: Docker check returned non-zero code. If database is running locally, continuing..." -ForegroundColor DarkYellow
    }
} catch {
    Write-Host "  Note: Docker check skipped." -ForegroundColor DarkYellow
}

# ------------------------------------------------------------------------------
# 3. Apply Alembic Database Migrations & Encryption Check
# ------------------------------------------------------------------------------
Write-Host "`n[3/5] Applying database migrations & encryption check..." -ForegroundColor Yellow
$BackendDir = Join-Path $WorkspaceRoot "backend"
$AlembicIni = Join-Path $WorkspaceRoot "alembic.ini"

try {
    Push-Location $BackendDir
    & $PythonExe -m alembic -c $AlembicIni upgrade head
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK: Database schema up to date" -ForegroundColor Green
    } else {
        Write-Host "  Warning: Alembic migration status $LASTEXITCODE" -ForegroundColor DarkYellow
    }

    & $PythonExe -m app.core.migrate_encryption
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK: Data encryption verified" -ForegroundColor Green
    }
} catch {
    Write-Host "  Warning: Migration step error: $($_.Exception.Message)" -ForegroundColor DarkYellow
} finally {
    Pop-Location
}

# ------------------------------------------------------------------------------
# 4. Clean up any existing listeners on Ports 8000 and 3000
# ------------------------------------------------------------------------------
Write-Host "`n[4/5] Preparing network ports (8000, 3000)..." -ForegroundColor Yellow

function Kill-PortOwner([int]$Port) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($conns) {
            foreach ($conn in $conns) {
                $pidToKill = $conn.OwningProcess
                if ($pidToKill -and ($pidToKill -ne 0) -and ($pidToKill -ne $PID)) {
                    Write-Host "  Stopping stale process $pidToKill on port $Port..." -ForegroundColor DarkGray
                    Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
                }
            }
        }
    } catch {
        # ignore
    }
}

Kill-PortOwner 8000
Kill-PortOwner 3000

# ------------------------------------------------------------------------------
# 5. Launch Backend & Frontend Services
# ------------------------------------------------------------------------------
Write-Host "`n[5/5] Launching Backend API & Next.js Website..." -ForegroundColor Yellow

# Create runtime logs folder if not present
$LogsDir = Join-Path $WorkspaceRoot ".runtime"
if (-not (Test-Path $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir | Out-Null }
$BackendLogOut = Join-Path $LogsDir "backend.stdout.log"
$BackendLogErr = Join-Path $LogsDir "backend.stderr.log"

# Start Backend API in background process
$BackendArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000")
if (-not $Production) {
    $BackendArgs += "--reload"
}

$backendProc = Start-Process -FilePath $PythonExe `
    -ArgumentList $BackendArgs `
    -WorkingDirectory $BackendDir `
    -PassThru `
    -RedirectStandardOutput $BackendLogOut `
    -RedirectStandardError $BackendLogErr `
    -NoNewWindow

Write-Host "  OK: Backend API process started (PID: $($backendProc.Id)) on http://127.0.0.1:8000" -ForegroundColor Green

# Wait for backend and database readiness (up to 15 seconds)
$backendReady = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health/ready" -TimeoutSec 1 -ErrorAction SilentlyContinue
        if ($resp -and ($resp.status -eq "ready") -and ($resp.database -eq "connected")) {
            $backendReady = $true
            break
        }
    } catch {
        # continue waiting
    }
}

if ($backendReady) {
    Write-Host "  OK: Backend API and database are ready" -ForegroundColor Green
} else {
    Write-Host "  Warning: Backend API/database did not become ready within 15 seconds." -ForegroundColor DarkYellow
    Write-Host "  Uploads and extraction will not work until the backend is healthy; check .runtime\backend.stderr.log." -ForegroundColor DarkYellow
}

# ------------------------------------------------------------------------------
# Summary & Frontend Launch
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
if ($backendReady) {
    Write-Host "  STACK IS READY & OPERATIONAL" -ForegroundColor Green
} else {
    Write-Host "  FRONTEND STARTED; BACKEND READINESS IS UNCONFIRMED" -ForegroundColor DarkYellow
}
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  - Web Application : http://localhost:3000" -ForegroundColor White
Write-Host "  - Backend API Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host "  - API Health Check: http://localhost:8000/api/v1/health/ready" -ForegroundColor White
Write-Host "  - Neo4j Graph View: http://localhost:7474" -ForegroundColor White
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Press Ctrl+C at any time to stop all services." -ForegroundColor DarkGray
Write-Host ""

# Start Frontend (blocking in foreground so user sees logs and can Ctrl+C)
try {
    $npmCmd = "npm.cmd"
    if (-not (Get-Command $npmCmd -ErrorAction SilentlyContinue)) { $npmCmd = "npm" }
    
    & $npmCmd run dev
} finally {
    Write-Host "`nStopping background services..." -ForegroundColor Yellow
    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
    Kill-PortOwner 8000
    Kill-PortOwner 3000
    Write-Host "All services stopped cleanly." -ForegroundColor Green
}
