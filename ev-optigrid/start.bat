@echo off
REM Starts the backend (port 8000) and frontend (port 3000) in two windows. Close both windows to stop.
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe ( echo Not set up yet. Run setup.bat first. & pause & exit /b 1 )
if not exist frontend\node_modules ( echo Frontend packages missing. Run setup.bat first. & pause & exit /b 1 )

start "EV-OptiGrid backend (port 8000)" cmd /k "cd /d %~dp0backend && .venv\Scripts\python -m uvicorn main:app --port 8000"
start "EV-OptiGrid frontend (port 3000)" cmd /k "cd /d %~dp0frontend && npm run dev"

echo Starting... your browser will open in a few seconds.
timeout /t 12 /nobreak >nul
start http://localhost:3000
