@echo off
title Defuse the Downloads - Launcher
color 0B
echo.
echo  =============================================
echo   ^> DEFUSE THE DOWNLOADS  v2.0  LAUNCHER
echo  =============================================
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [ERROR] Python not found in PATH.
        echo  Install Python from https://python.org and re-run.
        pause
        exit /b 1
    )
    set PYTHON=py
) else (
    set PYTHON=python
)

echo  [1/3] Installing Python dependencies...
%PYTHON% -m pip install -q flask flask-cors google-genai python-dotenv werkzeug
echo       Done.
echo.

echo  [2/3] Starting Flask backend on http://127.0.0.1:5000 ...
start "DTD Backend" cmd /k "%PYTHON% backend\app.py"
timeout /t 2 /nobreak >nul
echo       Backend started in new window.
echo.

echo  [3/3] Starting frontend server on http://localhost:8080 ...
start "DTD Frontend" cmd /k "%PYTHON% -m http.server 8080"
timeout /t 1 /nobreak >nul
echo.

echo  Opening game in browser...
start http://localhost:8080
echo.
echo  =============================================
echo   Game running at: http://localhost:8080
echo   Backend API at:  http://127.0.0.1:5000
echo  =============================================
echo.
echo  Close this window to keep servers running.
echo  Close the two server windows to stop the game.
pause
