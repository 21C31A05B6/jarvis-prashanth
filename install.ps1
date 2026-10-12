# ===============================================================================
# JARVIS OS -- One-Command PowerShell Automated Laptop Installer
# ===============================================================================
# Can be run directly on any Windows laptop:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
# Or from git:
#   git clone https://github.com/21C31A05B6/jarvis-prashanth.git; cd jarvis-prashanth; .\install.ps1
# ===============================================================================

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) { $ScriptDir = (Get-Location).Path }

# If run directly as a web one-liner without existing repo files, clone automatically:
if (-not (Test-Path (Join-Path $ScriptDir "main.py"))) {
    $TargetDir = Join-Path $HOME "jarvis-prashanth"
    if (-not (Test-Path $TargetDir)) {
        Write-Host "Cloning JARVIS repository into $TargetDir..." -ForegroundColor Cyan
        git clone https://github.com/21C31A05B6/jarvis-prashanth.git $TargetDir
    }
    Set-Location $TargetDir
    $ScriptDir = $TargetDir
}
Set-Location $ScriptDir

Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "           J . A . R . V . I . S   O S  --  A U T O - I N S T A L L E R        " -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Installing JARVIS OS on this computer..." -ForegroundColor Yellow
Write-Host "Project directory: $ScriptDir" -ForegroundColor Gray
Write-Host ""

# 1. Detect / Install Python
Write-Host "[1/6] Checking Python installation..." -ForegroundColor Cyan
$PythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCmd = "py -3"
} else {
    Write-Host "Python was not found. Attempting automatic installation via winget..." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $PythonCmd = "python"
    } else {
        Write-Error "Python 3.11+ is required. Please install from https://www.python.org/downloads/ and check 'Add python.exe to PATH'."
    }
}

Write-Host "[*] Python available: $PythonCmd" -ForegroundColor Green
& $PythonCmd --version

# 2. Virtual Environment Setup
Write-Host "`n[2/6] Configuring virtual environment..." -ForegroundColor Cyan
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[*] Creating fresh virtual environment in .\venv ..." -ForegroundColor Gray
    & $PythonCmd -m venv venv
} else {
    Write-Host "[*] Virtual environment already exists." -ForegroundColor Gray
}

# 3. Dependencies
Write-Host "`n[3/6] Installing dependencies..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip setuptools wheel --quiet
if (Test-Path (Join-Path $ScriptDir "requirements.txt")) {
    & $VenvPython -m pip install -r requirements.txt
} else {
    & $VenvPython -m pip install PyQt6 google-genai sounddevice numpy requests pillow
}

# 4. Environment config
Write-Host "`n[4/6] Checking configuration (.env)..." -ForegroundColor Cyan
$EnvPath = Join-Path $ScriptDir ".env"
$EnvExample = Join-Path $ScriptDir ".env.example"
if (-not (Test-Path $EnvPath)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvPath
        Write-Host "[*] Created .env from template." -ForegroundColor Green
    } else {
        Set-Content -Path $EnvPath -Value "GEMINI_API_KEY=`nGMAIL_SENDER=`nGMAIL_APP_PASSWORD=`n"
        Write-Host "[*] Created new .env file." -ForegroundColor Green
    }
} else {
    Write-Host "[*] Preserving existing .env file." -ForegroundColor Gray
}

# 5. Create Desktop and Startup Shortcuts
Write-Host "`n[5/6] Creating Desktop and Startup Voice Shortcuts..." -ForegroundColor Cyan
$DesktopDir = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$StartupDir = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Startup)
$VbsLauncher = Join-Path $ScriptDir "start_jarvis_voice.vbs"
$DevBat = Join-Path $ScriptDir "run_jarvis_dev.bat"

$ws = New-Object -ComObject WScript.Shell

# Desktop shortcut
$scDesk = $ws.CreateShortcut((Join-Path $DesktopDir "JARVIS OS.lnk"))
$scDesk.TargetPath = $VbsLauncher
$scDesk.WorkingDirectory = $ScriptDir
$scDesk.Description = "Launch JARVIS Voice & AI Assistant"
$scDesk.Save()

# Dev console shortcut
$scDev = $ws.CreateShortcut((Join-Path $DesktopDir "JARVIS Dev Console.lnk"))
$scDev.TargetPath = $DevBat
$scDev.WorkingDirectory = $ScriptDir
$scDev.Description = "Launch JARVIS with Dev Console"
$scDev.Save()

# Windows Startup shortcut (always-listening voice wake)
$scBoot = $ws.CreateShortcut((Join-Path $StartupDir "JARVIS_Voice_Wake.lnk"))
$scBoot.TargetPath = $VbsLauncher
$scBoot.WorkingDirectory = $ScriptDir
$scBoot.Description = "JARVIS Background Voice Wake Listener"
$scBoot.Save()

Write-Host "[*] Created: Desktop\JARVIS OS" -ForegroundColor Green
Write-Host "[*] Created: Desktop\JARVIS Dev Console" -ForegroundColor Green
Write-Host "[*] Registered: Windows Startup Voice Wake Listener" -ForegroundColor Green

# 6. Verify components
Write-Host "`n[6/6] Verifying system components..." -ForegroundColor Cyan
$env:QT_QPA_PLATFORM = "offscreen"
$env:JARVIS_SKIP_CLAP_GATE = "1"
& $VenvPython -c "import core.qt_init; import ui; print('[*] GUI HUD components: OK')"
& $VenvPython -c "import actions.todo_dialog; print('[*] To-Do Scheduler engine: OK')"

Write-Host ""
Write-Host "===============================================================================" -ForegroundColor Green
Write-Host "            J . A . R . V . I . S   I S   R E A D Y !                          " -ForegroundColor Green
Write-Host "===============================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "How to use JARVIS on this laptop:" -ForegroundColor Yellow
Write-Host "1. SAY 'Hey JARVIS': JARVIS is automatically listening in the background on boot."
Write-Host "2. DESKTOP ICON: Double-click 'JARVIS OS' on your Desktop anytime."
Write-Host "3. DEV CONSOLE: Run 'JARVIS Dev Console' to open with terminal logs."
Write-Host "4. API KEYS: Ensure your GEMINI_API_KEY is placed in your .env file."
Write-Host ""
