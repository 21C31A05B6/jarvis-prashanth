@echo off
setlocal EnableExtensions
title JARVIS Desktop Agent

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "JARVIS_CLI=1"
set "JARVIS_SKIP_CLAP_GATE=1"
set "JARVIS_HOSTED="

if exist "%ROOT%.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ROOT%.env") do (
    if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
  )
)
set "PY_CMD=python"
if exist "%ROOT%venv\Scripts\python.exe" set "PY_CMD=%ROOT%venv\Scripts\python.exe"
if exist "%ROOT%.venv\Scripts\python.exe" set "PY_CMD=%ROOT%.venv\Scripts\python.exe"

if /i not "%PY_CMD%"=="python" goto :python_path_ready
where python >nul 2>nul
if errorlevel 1 goto :python_missing
goto :python_path_ready

:python_missing
  echo [JARVIS] Python was not found. Install Python 3.11+ or create venv\.venv.
  pause
  exit /b 1

:python_path_ready

:: Check for pythonw to launch GUI window without extra console, or fallback to python
set "PYW_CMD="
if exist "%ROOT%venv\Scripts\pythonw.exe" (
  set "PYW_CMD=%ROOT%venv\Scripts\pythonw.exe"
) else if exist "%ROOT%.venv\Scripts\pythonw.exe" (
  set "PYW_CMD=%ROOT%.venv\Scripts\pythonw.exe"
) else (
  where pythonw >nul 2>nul
  if not errorlevel 1 set "PYW_CMD=pythonw"
)

echo [JARVIS] Opening To-Do ^& Task Scheduler Window...
echo [JARVIS] Enter your tasks and click 'OK - START JARVIS' to proceed...
if defined PYW_CMD (
  start /wait "" "%PYW_CMD%" -m actions.todo_dialog
) else (
  "%PY_CMD%" -m actions.todo_dialog
)

echo [JARVIS] Starting interactive desktop agent...
echo [JARVIS] Speak to JARVIS or use the desktop controls to give tasks.
echo [JARVIS] Press Ctrl+C in this window to stop the agent.
echo.
set "JARVIS_SKIP_TODO_PROMPT=1"
"%PY_CMD%" main.py
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo [JARVIS] Agent stopped with exit code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
