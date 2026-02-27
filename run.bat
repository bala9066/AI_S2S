@echo off
setlocal enabledelayedexpansion
title AI Hardware Design Pipeline - S2S

echo.
echo  ============================================================
echo   AI Hardware Design Pipeline  ^|  S2S V2
echo  ============================================================
echo.

REM ── Find Python ────────────────────────────────────────────────
set PYTHON_CMD=

for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined PYTHON_CMD (
        py -%%V --version >nul 2>&1
        if !errorlevel!==0 (
            set PYTHON_CMD=py -%%V
            echo [OK] Python %%V found
        )
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] Python 3.10 or newer is required.
    echo         Download from: https://python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM ── Install / upgrade dependencies ────────────────────────────
echo.
echo [1/3] Installing dependencies (this may take a minute on first run)...
%PYTHON_CMD% -m pip install -r requirements.txt -q --no-warn-script-location
if errorlevel 1 (
    echo [WARN] Some packages may have failed to install.
    echo        Check requirements.txt or run pip manually.
)

REM ── Kill any stale processes on our ports ─────────────────────
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":8000 "') do (
    taskkill /PID %%P /F >nul 2>&1
)
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":8501 "') do (
    taskkill /PID %%P /F >nul 2>&1
)

REM ── Start FastAPI backend ──────────────────────────────────────
echo.
echo [2/3] Starting FastAPI backend on http://localhost:8000 ...
start "S2S - FastAPI Backend" cmd /k "title S2S FastAPI Backend && %PYTHON_CMD% -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info"

REM ── Wait for backend to be ready ──────────────────────────────
echo       Waiting for backend to be ready...
set /a TRIES=0
:waitloop
timeout /t 2 /nobreak >nul
%PYTHON_CMD% -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" >nul 2>&1
if errorlevel 1 (
    set /a TRIES+=1
    if !TRIES! lss 15 goto :waitloop
    echo [WARN] Backend health check timed out. Proceeding anyway...
) else (
    echo [OK]  Backend is healthy.
)

REM ── Start Streamlit UI ─────────────────────────────────────────
echo.
echo [3/3] Starting Streamlit UI on http://localhost:8501 ...
start "S2S - Streamlit UI" cmd /k "title S2S Streamlit UI && %PYTHON_CMD% -m streamlit run app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false"

timeout /t 4 /nobreak >nul

REM ── Open browser ──────────────────────────────────────────────
echo.
echo  ============================================================
echo   Application started!
echo.
echo   UI    →  http://localhost:8501
echo   API   →  http://localhost:8000/docs
echo  ============================================================
echo.
echo  Two terminal windows have opened:
echo    "S2S - FastAPI Backend"  (keep this running)
echo    "S2S - Streamlit UI"     (keep this running)
echo.
echo  Close this window when you're done.
echo.

start http://localhost:8501

pause
