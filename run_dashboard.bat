@echo off
setlocal
echo ===================================================
echo   JARVIS COMMAND CENTER HUD - WEB DASHBOARD
echo ===================================================
cd /d "%~dp0web"

if not exist "node_modules" (
  echo [JARVIS] Installing web dependencies...
  call npm.cmd install
)

echo [JARVIS] Starting Next.js Dev Server on http://localhost:3000 ...
start http://localhost:3000
call npm.cmd run dev

pause
