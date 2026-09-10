@echo off
:: ============================================================
:: JARVIS Launcher — keys are loaded from .env automatically
:: Copy .env.example to .env and fill in your keys first.
:: ============================================================
set PYTHONUTF8=1
set JARVIS_CLI=1
set JARVIS_SKIP_CLAP_GATE=1

:: Load .env if it exists
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
  )
)

python main.py
pause
