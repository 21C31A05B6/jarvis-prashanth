@echo off
:: ============================================================
:: JARVIS Auto-Start Script — Wake Word Mode
:: Launched automatically at Windows login via Task Scheduler.
:: JARVIS runs silently in the background, listening for
:: "Hey JARVIS" before fully activating the interface.
:: ============================================================

:: Change to the JARVIS project directory
cd /d "%~dp0.."

:: Set environment flags
set PYTHONUTF8=1
set JARVIS_CLI=1

:: Skip the clap gate — boot directly to wake-word listening
set JARVIS_SKIP_CLAP_GATE=1

:: Enable wake-word-only mode: JARVIS waits silently until
:: it hears "Hey JARVIS" before launching the full UI.
set JARVIS_WAKE_WORD_ONLY=1

:: Load keys from .env (copy .env.example to .env and fill in your keys)
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
  )
)

:: Start the JARVIS process minimized (no console window stealing focus)
start "JARVIS" /MIN python main.py
