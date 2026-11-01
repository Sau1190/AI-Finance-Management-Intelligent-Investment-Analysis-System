@echo off
REM One-click local demo for Windows. Uses SQLite (no Docker/PostgreSQL needed).
REM Needs Python 3.11+ and Node.js 20+ installed and on PATH.
REM Your real data stays in backend\demo.db and backend\storage (both git-ignored).
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python was not found. Install Python 3.11+ and tick "Add to PATH". & goto :fail)
where npm >nul 2>nul || (echo Node.js/npm was not found. Install Node.js LTS from nodejs.org. & goto :fail)

if not exist backend\.venv\Scripts\python.exe (
  echo First-time setup: creating the Python environment ^(a few minutes^)...
  python -m venv backend\.venv || goto :fail
  backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt || goto :fail
)
if not exist frontend\node_modules (
  echo First-time setup: installing the dashboard packages...
  pushd frontend
  call npm install || (popd & goto :fail)
  popd
)
REM API keys (optional) go in .env at the project root. The dashboard never holds keys.
if not exist .env copy .env.example .env >nul

REM Child windows inherit this; it overrides DATABASE_URL in .env for the demo only.
set "DATABASE_URL=sqlite+pysqlite:///./demo.db"

start "Backend API (port 8000)" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "Dashboard (port 5173)" cmd /k "cd /d %~dp0frontend && npm run dev -- --host 127.0.0.1"
echo Waiting for the servers to start...
timeout /t 8 /nobreak >nul
start "" http://127.0.0.1:5173
echo.
echo The dashboard should open in your browser. Close the two server windows to stop.
exit /b 0

:fail
echo.
echo Setup did not finish. Read the message above, fix it, and run this file again.
pause
exit /b 1
