@echo off
REM One-time setup for Windows: double-click this file, or run  setup.bat  in a terminal.
setlocal
cd /d "%~dp0"

echo == Checking Python (need 3.10, 3.11 or 3.12)
where python >nul 2>nul || (echo Python not found. Install Python 3.12 from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)" || (echo This project needs Python 3.10, 3.11 or 3.12. The pinned NumPy/SciPy have no packages for 3.13+. Install Python 3.12 and try again. & pause & exit /b 1)

echo == Checking Node.js (need 18 or newer)
where node >nul 2>nul || (echo Node.js not found. Install the LTS version from https://nodejs.org/ & pause & exit /b 1)
node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 18 ? 0 : 1)" || (echo Node is too old. Install Node 20 or 22 LTS. & pause & exit /b 1)

echo == Backend: virtual environment + packages (first time takes a few minutes)
if not exist backend\.venv ( python -m venv backend\.venv || (pause & exit /b 1) )
backend\.venv\Scripts\python -m pip install --quiet --upgrade pip
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt || (echo Package install failed. See the message above. & pause & exit /b 1)

echo == Backend: settings + local database
if not exist backend\.env copy backend\.env.example backend\.env >nul
pushd backend
.venv\Scripts\python scripts\init_db.py || (popd & pause & exit /b 1)
popd

echo == Frontend: packages
pushd frontend
call npm install --no-audit --no-fund || (popd & pause & exit /b 1)
popd

echo.
echo Setup complete. Start the app by double-clicking start.bat, then open http://localhost:3000
pause
