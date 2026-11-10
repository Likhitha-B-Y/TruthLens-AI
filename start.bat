@echo off
REM ===========================================================================
REM  TruthLens AI - Windows launcher
REM    start.bat          set up (first run) and start the app at http://localhost:8000
REM    start.bat dev      backend + Vite dev server with hot reload (needs Node.js), http://localhost:5173
REM    start.bat models   download the AI models now (roughly 0.5-1 GB) instead of on first use
REM    start.bat test     run the backend test-suite
REM    start.bat setup    only create the virtual environment and install dependencies
REM ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
set MODE=%1
if "%MODE%"=="" set MODE=prod

set PY=python
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python was not found. Install Python 3.10, 3.11 or 3.12 from https://www.python.org/downloads/
    echo         and tick "Add python.exe to PATH" during installation.
    pause
    exit /b 1
  )
  set PY=py -3
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating virtual environment in .venv ...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)
set VPY=.venv\Scripts\python.exe

if not exist ".venv\.deps_installed" (
  echo [2/3] Installing Python dependencies - this can take several minutes the first time ...
  "%VPY%" -m pip install --upgrade pip
  "%VPY%" -m pip install -r backend\requirements.txt
  if errorlevel 1 goto :fail
  echo ok> ".venv\.deps_installed"
)

if /i "%MODE%"=="setup" (
  echo Setup complete.
  exit /b 0
)
if /i "%MODE%"=="models" (
  "%VPY%" backend\scripts\download_models.py
  pause
  exit /b %errorlevel%
)
if /i "%MODE%"=="test" (
  pushd backend
  "..\%VPY%" -m pytest -q
  popd
  pause
  exit /b %errorlevel%
)

if /i "%MODE%"=="dev" (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Node.js is required for dev mode. Install it from https://nodejs.org/ or run start.bat without arguments.
    pause
    exit /b 1
  )
  if not exist "frontend\node_modules" (
    echo Installing frontend packages ...
    pushd frontend
    call npm install
    popd
  )
  echo Starting backend on http://localhost:8000 and frontend on http://localhost:5173 ...
  start "TruthLens backend" cmd /k "cd /d %~dp0backend && ..\%VPY% -m uvicorn app.main:get_app --factory --reload --port 8000"
  pushd frontend
  call npm run dev -- --open
  popd
  exit /b 0
)

REM ---- default: production mode (backend serves the pre-built UI) ----
if not exist "frontend\dist\index.html" (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] frontend\dist is missing and Node.js is not installed to build it.
    echo         Install Node.js from https://nodejs.org/ and run start.bat again.
    pause
    exit /b 1
  )
  echo [3/3] Building the frontend ...
  pushd frontend
  call npm install
  call npm run build
  popd
)
echo.
echo  TruthLens AI is starting at http://localhost:8000
echo  API documentation:        http://localhost:8000/docs
echo  The first verification downloads the AI models once (roughly 0.5-1 GB). Keep this window open.
echo.
start "" cmd /c "timeout /t 6 /nobreak >nul & start http://localhost:8000"
pushd backend
"..\%VPY%" -m uvicorn app.main:get_app --factory --host 127.0.0.1 --port 8000
popd
pause
exit /b 0

:fail
echo.
echo [ERROR] Setup failed. See the messages above. Common fixes: use Python 3.10-3.12, check your internet connection.
pause
exit /b 1
