@echo off
REM start.bat — Launch Scholar Tracker (backend + bridge) in one terminal
cd /d "%~dp0"

REM Ensure node/npm are in PATH (venv activation can hide them)
where node >nul 2>&1 || set "PATH=%PATH%;C:\Program Files\nodejs;%APPDATA%\nvm"
where python >nul 2>&1 || (echo ERROR: python not found & pause & exit /b 1)
where node   >nul 2>&1 || (echo ERROR: node not found. Install from https://nodejs.org & pause & exit /b 1)

REM Setup Python venv if needed
if not exist ".venv" (
    echo Creating Python venv...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -e . --quiet 2>nul
call deactivate 2>nul

REM Restore node in PATH after deactivate
where node >nul 2>&1 || set "PATH=%PATH%;C:\Program Files\nodejs;%APPDATA%\nvm"

REM Install Node deps if needed
if not exist "bridge\node_modules" (
    echo Installing bridge dependencies...
    pushd bridge && call npm install && popd
)

REM Copy .env if missing
if not exist ".env" (
    copy .env.example .env >nul
    echo Created .env from .env.example — edit it if needed.
)

echo.
echo Starting backend + bridge...
echo Press Ctrl+C to stop both.
echo.

start /b "" ".venv\Scripts\python.exe" main.py
timeout /t 2 /nobreak >nul
start /b "" node bridge\index.js

pause >nul
