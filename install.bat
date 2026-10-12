@echo off
setlocal EnableExtensions EnableDelayedExpansion
title JARVIS OS — Complete Laptop Installer
color 0B

echo ===============================================================================
echo            J . A . R . V . I . S   O S  --  A U T O - I N S T A L L E R
echo ===============================================================================
echo.
echo  Initializing automated setup for this machine...
echo.

set "ROOT=%~dp0"
cd /d "%ROOT%"

:: 1. Check for Python
echo [1/6] Checking Python installation...
set "HOST_PYTHON="
where python >nul 2>nul
if not errorlevel 1 (
  set "HOST_PYTHON=python"
) else (
  where py >nul 2>nul
  if not errorlevel 1 set "HOST_PYTHON=py -3"
)

if not defined HOST_PYTHON (
  echo [!] Python was not found on this system.
  where winget >nul 2>nul
  if not errorlevel 1 (
    echo [*] Found Windows Package Manager (winget).
    echo [*] Installing Python 3.11 automatically...
    winget install -e --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
    echo [*] Refreshing PATH...
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
    set "HOST_PYTHON=python"
  ) else (
    echo [ERROR] Python 3.11+ is required but not installed.
    echo Please install Python 3.11 or 3.12 from https://www.python.org/downloads/
    echo Make sure to CHECK "Add python.exe to PATH" during installation!
    echo.
    pause
    exit /b 1
  )
)

echo [*] Using Python: %HOST_PYTHON%
%HOST_PYTHON% --version

:: 2. Create Virtual Environment
echo.
echo [2/6] Setting up virtual environment (venv)...
if not exist "venv\Scripts\python.exe" (
  echo [*] Creating fresh virtual environment in .\venv ...
  %HOST_PYTHON% -m venv venv
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
  )
) else (
  echo [*] Virtual environment already exists at .\venv
)

set "VENV_PY=%ROOT%venv\Scripts\python.exe"

:: 3. Upgrade pip and install dependencies
echo.
echo [3/6] Installing JARVIS core dependencies and AI packages...
echo [*] Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel --quiet

if exist "requirements.txt" (
  echo [*] Installing packages from requirements.txt...
  "%VENV_PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [WARNING] Some dependencies had warnings; retrying core packages...
    "%VENV_PY%" -m pip install PyQt6 google-genai sounddevice numpy requests pillow
  )
) else (
  echo [*] requirements.txt not found, installing base stack...
  "%VENV_PY%" -m pip install PyQt6 google-genai sounddevice numpy requests pillow
)

:: 4. Environment & Secrets setup
echo.
echo [4/6] Configuring environment settings...
if not exist ".env" (
  if exist ".env.example" (
    copy /y ".env.example" ".env" >nul
    echo [*] Created .env configuration file from template.
  ) else (
    echo GEMINI_API_KEY=>.env
    echo [*] Created new .env file.
  )
  echo [!] NOTE: Remember to add your GEMINI_API_KEY inside the .env file!
) else (
  echo [*] Existing .env file detected and preserved.
)

:: 5. Create Desktop & Startup Voice Shortcuts
echo.
echo [5/6] Creating Desktop and Windows Startup voice shortcuts...

set "DESKTOP_DIR=%USERPROFILE%\Desktop"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS_LAUNCHER=%ROOT%start_jarvis_voice.vbs"
set "DEV_BAT=%ROOT%run_jarvis_dev.bat"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$scDesk = $ws.CreateShortcut('%DESKTOP_DIR%\JARVIS OS.lnk'); " ^
  "$scDesk.TargetPath = '%VBS_LAUNCHER%'; " ^
  "$scDesk.WorkingDirectory = '%ROOT%'; " ^
  "$scDesk.Description = 'Launch JARVIS Voice & AI Assistant'; " ^
  "$scDesk.Save(); " ^
  "$scDev = $ws.CreateShortcut('%DESKTOP_DIR%\JARVIS Dev Console.lnk'); " ^
  "$scDev.TargetPath = '%DEV_BAT%'; " ^
  "$scDev.WorkingDirectory = '%ROOT%'; " ^
  "$scDev.Description = 'Launch JARVIS with Dev Console'; " ^
  "$scDev.Save(); " ^
  "$scBoot = $ws.CreateShortcut('%STARTUP_DIR%\JARVIS_Voice_Wake.lnk'); " ^
  "$scBoot.TargetPath = '%VBS_LAUNCHER%'; " ^
  "$scBoot.WorkingDirectory = '%ROOT%'; " ^
  "$scBoot.Description = 'JARVIS Background Voice Wake Listener'; " ^
  "$scBoot.Save();"

echo [*] Desktop shortcut created: JARVIS OS
echo [*] Desktop shortcut created: JARVIS Dev Console
echo [*] Windows Startup voice wake listener registered!

:: 6. Verification
echo.
echo [6/6] Verifying JARVIS core integrity...
set "QT_QPA_PLATFORM=offscreen"
set "JARVIS_SKIP_CLAP_GATE=1"
"%VENV_PY%" -c "import core.qt_init; import ui; print('[*] GUI HUD components: OK')"
"%VENV_PY%" -c "import actions.todo_dialog; print('[*] To-Do Scheduler engine: OK')"

echo.
echo ===============================================================================
echo            J . A . R . V . I . S   I S   R E A D Y !
echo ===============================================================================
echo.
echo  Installation completed successfully on this laptop!
echo.
echo  How to use JARVIS:
echo  -----------------------------------------------------------------------------
echo  1. ALWAYS-LISTENING VOICE WAKE:
echo     Whenever your laptop boots or turns on, JARVIS listens in the background.
echo     Just say out loud: "Hey JARVIS" (or "Hay JARVIS") to open the interface!
echo.
echo  2. DESKTOP ICON:
echo     Double-click the "JARVIS OS" icon on your Desktop anytime.
echo.
echo  3. API KEY:
echo     Make sure your GEMINI_API_KEY is saved inside the .env file.
echo.
echo ===============================================================================
echo.
pause
