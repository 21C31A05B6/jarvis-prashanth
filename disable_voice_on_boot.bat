@echo off
setlocal EnableExtensions
title Disable JARVIS Voice Wake on Boot

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\JARVIS_Voice_Wake.lnk"

if exist "%SHORTCUT_PATH%" (
  del /f /q "%SHORTCUT_PATH%"
  echo [SUCCESS] Removed JARVIS Voice Wake from Windows Startup.
) else (
  echo [INFO] JARVIS Voice Wake was not registered in Startup.
)

echo.
pause
