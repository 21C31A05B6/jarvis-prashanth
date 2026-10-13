@echo off
setlocal
:: ============================================================
:: JARVIS Launcher — automatically detects venv and loads .env
:: ============================================================
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set JARVIS_CLI=1
set JARVIS_SKIP_CLAP_GATE=1

cd /d "%~dp0"

:: Detect python in venv, .venv, or system PATH
set "PY_CMD=python"
if exist "venv\Scripts\python.exe" (
  set "PY_CMD=venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
  set "PY_CMD=.venv\Scripts\python.exe"
)

:: Load .env if it exists
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
  )
)

echo [JARVIS] Opening To-Do ^& Task Scheduler Window...
echo [JARVIS] Enter your tasks and click 'OK - START JARVIS' to proceed...
"%PY_CMD%" -m actions.todo_dialog

echo [JARVIS] Starting JARVIS AI Core using %PY_CMD%...
set "JARVIS_SKIP_TODO_PROMPT=1"
"%PY_CMD%" main.py
pause
