# ============================================================
# CivicLens Backend — Clean Start Script
# Run this INSTEAD of calling uvicorn directly.
# It kills all stale Python processes first to prevent
# zombie socket accumulation on Windows.
# ============================================================

Write-Host "=== CivicLens Backend Startup ===" -ForegroundColor Cyan

# Step 1: Kill ALL Python processes (uvicorn workers, reloaders, etc.)
Write-Host ">> Stopping all Python processes..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process python3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 1

# Step 2: Wait for OS to release TIME_WAIT sockets
Write-Host ">> Waiting for sockets to drain..." -ForegroundColor Yellow
Start-Sleep 4

# Step 3: Confirm port 8001 is clear
$occupied = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
if ($occupied) {
    Write-Host "WARNING: Port 8001 still has connections. Waiting a few more seconds..." -ForegroundColor Red
    Start-Sleep 5
}

# Step 4: Start uvicorn fresh
Write-Host ">> Starting CivicLens backend on http://127.0.0.1:8001 ..." -ForegroundColor Green
python -m uvicorn app.main:app --reload --port 8001 --log-level info
