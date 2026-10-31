# Defuse the Downloads — PowerShell Launcher
# Run: .\start.ps1

$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host " ================================================" -ForegroundColor Cyan
Write-Host "   ⚡  DEFUSE THE DOWNLOADS  v2.0  LAUNCHER" -ForegroundColor Cyan
Write-Host " ================================================" -ForegroundColor Cyan
Write-Host ""

# Locate Python or uv
$UV = "C:\Users\lavit\.local\bin\uv.exe"
if (Test-Path $UV) {
    Write-Host " Using uv environment manager ($UV)" -ForegroundColor Green
    $backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    Start-Process -FilePath $UV -ArgumentList "run --with flask --with flask-cors --with google-genai --with python-dotenv --with werkzeug python backend/app.py" -WorkingDirectory $backendDir -WindowStyle Normal
    Start-Sleep 2
    Start-Process "http://localhost:5000"
    Write-Host " ================================================" -ForegroundColor Cyan
    Write-Host "   Single-Server Game & API: http://localhost:5000" -ForegroundColor White
    Write-Host " ================================================" -ForegroundColor Cyan
    Read-Host "Press Enter to exit launcher (server keeps running)"
    exit 0
}

$PYTHON = $null
foreach ($cmd in @("python3","python","py")) {
    try {
        $v = & $cmd --version 2>&1
        if ($v -match "Python 3") { $PYTHON = $cmd; break }
    } catch {}
}
if (-not $PYTHON) {
    Write-Host " [ERROR] Python 3 not found. Install from https://python.org" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host " Python: $PYTHON" -ForegroundColor Green

# Install deps
Write-Host ""
Write-Host " [1/3] Installing Python dependencies..." -ForegroundColor Yellow
& $PYTHON -m pip install -q flask flask-cors google-genai
Write-Host "       ✓ flask, flask-cors, google-genai installed" -ForegroundColor Green

# Start Flask backend
Write-Host ""
Write-Host " [2/3] Starting Flask backend on http://127.0.0.1:5000 ..." -ForegroundColor Yellow
$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Start-Process -FilePath $PYTHON -ArgumentList "backend/app.py" -WorkingDirectory $backendDir -WindowStyle Normal
Start-Sleep 2
Write-Host "       ✓ Backend started" -ForegroundColor Green

# Start frontend HTTP server
Write-Host ""
Write-Host " [3/3] Starting frontend server on http://localhost:8080 ..." -ForegroundColor Yellow
Start-Process -FilePath $PYTHON -ArgumentList "-m","http.server","8080" -WorkingDirectory $backendDir -WindowStyle Minimized
Start-Sleep 1
Write-Host "       ✓ Frontend server started" -ForegroundColor Green

# Open browser
Write-Host ""
Start-Process "http://localhost:8080"

Write-Host ""
Write-Host " ================================================" -ForegroundColor Cyan
Write-Host "   Game:    http://localhost:8080" -ForegroundColor White
Write-Host "   Backend: http://127.0.0.1:5000" -ForegroundColor White
Write-Host " ================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " Files are in: $(Split-Path -Parent $MyInvocation.MyCommand.Path)" -ForegroundColor Gray
Write-Host "   📁 Messy_Downloads/   ← game spawns files here" -ForegroundColor Gray
Write-Host "   📂 Organized_Safe/    ← RMB organizes here" -ForegroundColor Gray
Write-Host "   🗑️  Trash_Bin/         ← LMB trashes here" -ForegroundColor Gray
Write-Host ""
Read-Host "Press Enter to exit launcher (servers keep running)"
