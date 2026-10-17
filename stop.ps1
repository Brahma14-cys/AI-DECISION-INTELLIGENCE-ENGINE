# ==============================================================================
# AI Legal Engine - Unified Stack Shutdown Script
# ==============================================================================
# Usage:
#   .\stop.ps1
#   npm run stop:all
#   .\stop.ps1 -Docker   (also stops docker containers)
# ==============================================================================

[CmdletBinding()]
param(
    [switch]$Docker
)

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Stopping AI Legal Decision Intelligence Stack" -ForegroundColor White
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

function Kill-PortOwner([int]$Port) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($conns) {
            foreach ($conn in $conns) {
                $pidToKill = $conn.OwningProcess
                if ($pidToKill -and ($pidToKill -ne 0)) {
                    Write-Host "  Stopping process $pidToKill on port $Port..." -ForegroundColor Yellow
                    Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
                }
            }
        }
    } catch {
        # ignore
    }
}

# 1. Stop web ports
Kill-PortOwner 3000
Kill-PortOwner 8000

# 2. Stop any orphaned uvicorn processes
try {
    $uvicornProcs = Get-Process -Name uvicorn -ErrorAction SilentlyContinue
    if ($uvicornProcs) {
        $uvicornProcs | Stop-Process -Force -ErrorAction SilentlyContinue
    }
} catch {
    # ignore
}

# 3. Optional docker stop
if ($Docker) {
    Write-Host "Stopping Docker containers..." -ForegroundColor Yellow
    try {
        docker compose down
        Write-Host "  OK: Docker containers stopped" -ForegroundColor Green
    } catch {
        Write-Host "  Warning: Docker stop skipped: $($_.Exception.Message)" -ForegroundColor DarkYellow
    }
}

Write-Host "  OK: All ports (3000, 8000) and web services closed." -ForegroundColor Green
Write-Host ""
