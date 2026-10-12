@echo off
setlocal EnableExtensions
title Enable JARVIS Voice Wake on Boot

set "ROOT=%~dp0"
set "VBS_PATH=%ROOT%start_jarvis_voice.vbs"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\JARVIS_Voice_Wake.lnk"

echo ============================================================
echo  JARVIS — Enable Always-Listening Voice Wake on PC Startup
echo ============================================================
echo.

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%VBS_PATH%'; $s.WorkingDirectory = '%ROOT%'; $s.WindowStyle = 7; $s.Save()"

if exist "%SHORTCUT_PATH%" (
  echo [SUCCESS] JARVIS Voice Wake registered for Windows Startup!
  echo Location: %SHORTCUT_PATH%
  echo.
  echo Whenever you turn on your PC or log in, JARVIS will be silently
  echo listening in the background. Just say "Hey JARVIS" to launch!
) else (
  echo [ERROR] Failed to create shortcut.
)

echo.
pause
