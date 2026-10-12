@echo off
setlocal EnableExtensions
title JARVIS Voice Wake Listener

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "JARVIS_CLI=1"
set "JARVIS_SKIP_CLAP_GATE=1"
set "JARVIS_WAKE_WORD_ONLY=1"
set "JARVIS_HOSTED="

:: Load .env
if exist "%ROOT%.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ROOT%.env") do (
    if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
  )
)

:: Detect Python executable
set "PY_CMD=python"
if exist "%ROOT%venv\Scripts\python.exe" set "PY_CMD=%ROOT%venv\Scripts\python.exe"
if exist "%ROOT%.venv\Scripts\python.exe" set "PY_CMD=%ROOT%.venv\Scripts\python.exe"

set "PYW_CMD="
if exist "%ROOT%venv\Scripts\pythonw.exe" (
  set "PYW_CMD=%ROOT%venv\Scripts\pythonw.exe"
) else if exist "%ROOT%.venv\Scripts\pythonw.exe" (
  set "PYW_CMD=%ROOT%.venv\Scripts\pythonw.exe"
) else (
  where pythonw >nul 2>nul
  if not errorlevel 1 set "PYW_CMD=pythonw"
)

if defined PYW_CMD (
  "%PYW_CMD%" main.py
) else (
  "%PY_CMD%" main.py
)
