@echo off
setlocal enabledelayedexpansion
title SupoClip Launcher

echo ===================================================
echo             SupoClip One-Click Launcher
echo ===================================================
echo.

set ROOT_DIR=%~dp0
set BACKEND_DIR=%ROOT_DIR%backend
set FRONTEND_DIR=%ROOT_DIR%frontend
set PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe
set PG_BIN=C:\Users\Hp\pgsql\bin
set PG_DATA=C:\Users\Hp\pgsql\data

:: -----------------------------------------------------
:: 1. Verify / Start Redis Service
:: -----------------------------------------------------
echo [*] Checking Redis service...
sc query Redis | find "RUNNING" >nul 2>&1
if errorlevel 1 (
    echo [!] Redis is not running. Attempting to start Redis...
    net start Redis >nul 2>&1
    if errorlevel 1 (
        echo [!] WARNING: Could not start Redis Windows service. Please ensure Redis is running on port 6379.
    ) else (
        echo [OK] Redis service started successfully.
    )
) else (
    echo [OK] Redis is running.
)

:: -----------------------------------------------------
:: 2. Verify / Start PostgreSQL
:: -----------------------------------------------------
echo [*] Checking PostgreSQL server on port 5432...
netstat -ano | find "0.0.0.0:5432" >nul 2>&1
if errorlevel 1 (
    netstat -ano | find "127.0.0.1:5432" >nul 2>&1
)
if errorlevel 1 (
    echo [!] PostgreSQL is not running. Starting PostgreSQL...
    if exist "%PG_DATA%\postmaster.pid" (
        del /f /q "%PG_DATA%\postmaster.pid" >nul 2>&1
    )
    if exist "%PG_BIN%\pg_ctl.exe" (
        "%PG_BIN%\pg_ctl.exe" -D "%PG_DATA%" start >nul 2>&1
        timeout /t 2 /nobreak >nul
        echo [OK] PostgreSQL server started.
    ) else (
        echo [!] WARNING: pg_ctl.exe not found at %PG_BIN%. Ensure Postgres is running on port 5432.
    )
) else (
    echo [OK] PostgreSQL is active on port 5432.
)

:: -----------------------------------------------------
:: 3. Start FastAPI Backend (Title: SupoClip Backend)
:: -----------------------------------------------------
echo [*] Launching FastAPI Backend on port 8000...
start "SupoClip Backend" cmd /k "cd /d "%BACKEND_DIR%" && "%PYTHON_EXE%" -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload"

:: -----------------------------------------------------
:: 4. Start ARQ Worker (Title: SupoClip Worker)
:: -----------------------------------------------------
echo [*] Launching ARQ Background Worker...
start "SupoClip Worker" cmd /k "cd /d "%BACKEND_DIR%" && "%PYTHON_EXE%" -m arq src.workers.tasks.WorkerSettings"

:: -----------------------------------------------------
:: 5. Start Frontend Dev Server (Title: SupoClip Frontend)
:: -----------------------------------------------------
echo [*] Launching Next.js Frontend on port 3107...
start "SupoClip Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && pnpm dev"

:: -----------------------------------------------------
:: 6. Wait & Open Browser
:: -----------------------------------------------------
echo.
echo [*] Waiting for services to bind...
timeout /t 4 /nobreak >nul

echo [OK] Opening SupoClip Dashboard in your browser...
start http://localhost:3107

echo.
echo ===================================================
echo       All SupoClip services are up and running!
echo    Run stop_server.bat whenever you want to stop.
echo ===================================================
timeout /t 3 /nobreak >nul
