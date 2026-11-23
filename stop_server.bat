@echo off
setlocal
title SupoClip Stopper

echo ===================================================
echo             Stopping SupoClip Services
echo ===================================================
echo.

echo [*] Closing SupoClip Backend, Worker, and Frontend windows...
taskkill /fi "WINDOWTITLE eq SupoClip Backend*" /f /t >nul 2>&1
taskkill /fi "WINDOWTITLE eq SupoClip Worker*" /f /t >nul 2>&1
taskkill /fi "WINDOWTITLE eq SupoClip Frontend*" /f /t >nul 2>&1

:: Also terminate any dangling node/python dev processes on ports 8000 & 3107
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8000" ^| find "LISTENING"') do (
    taskkill /pid %%a /f >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| find ":3107" ^| find "LISTENING"') do (
    taskkill /pid %%a /f >nul 2>&1
)

echo [OK] All SupoClip server processes stopped.
timeout /t 2 /nobreak >nul
