# ================================================================
# JARVIS Auto-Start Installer
# Run this script ONCE as Administrator to register JARVIS in
# Windows Task Scheduler so it launches automatically at login.
#
# Usage (in PowerShell as Admin):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\startup\install_autostart.ps1
# ================================================================

param(
    [string]$TaskName = "JARVIS Auto-Start",
    [switch]$Uninstall
)

# --- Resolve paths ---
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir   = Split-Path -Parent $ScriptDir
$StartupBat   = Join-Path $ScriptDir "jarvis_autostart.bat"
$VenvPython   = Join-Path $ProjectDir "venv\Scripts\pythonw.exe"
$SystemPython = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)?.Source

# ----------------------------------------------------------------
# UNINSTALL mode
# ----------------------------------------------------------------
if ($Uninstall) {
    Write-Host "Removing Task Scheduler entry '$TaskName'..." -ForegroundColor Yellow
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "✅ Task removed successfully." -ForegroundColor Green
    } catch {
        Write-Host "⚠️  Task not found or could not be removed: $_" -ForegroundColor Red
    }
    exit 0
}

# ----------------------------------------------------------------
# INSTALL mode
# ----------------------------------------------------------------
Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     JARVIS Auto-Start Installer              ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check the startup bat exists
if (-not (Test-Path $StartupBat)) {
    Write-Host "❌ Could not find: $StartupBat" -ForegroundColor Red
    Write-Host "   Make sure you are running from the JARVIS project folder." -ForegroundColor Red
    exit 1
}

# Determine Python executable (prefer venv's pythonw for windowless launch)
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
    Write-Host "✅ Using venv Python: $PythonExe" -ForegroundColor Green
} elseif ($SystemPython) {
    $PythonExe = $SystemPython
    Write-Host "⚠️  Using system Python: $PythonExe" -ForegroundColor Yellow
} else {
    # Fall back to the .bat launcher which handles PATH itself
    $PythonExe = $null
    Write-Host "⚠️  pythonw.exe not found — will use the .bat launcher directly." -ForegroundColor Yellow
}

# Build the action
if ($PythonExe) {
    # Run pythonw (no console window) directly with main.py
    $Action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument "`"$(Join-Path $ProjectDir 'main.py')`"" `
        -WorkingDirectory $ProjectDir
} else {
    # Fallback: run the bat file hidden via cmd
    $Action = New-ScheduledTaskAction `
        -Execute "cmd.exe" `
        -Argument "/C `"$StartupBat`"" `
        -WorkingDirectory $ProjectDir
}

# Trigger: at logon of the current user
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Settings: allow running on battery, hidden, restart on failure
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -Hidden `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# Principal: run as current user, no elevation needed
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

# Environment variables for the task
$EnvXml = @"
<EnvironmentVariables>
  <EnvironmentVariable>
    <Name>JARVIS_CLI</Name><Value>1</Value>
  </EnvironmentVariable>
  <EnvironmentVariable>
    <Name>JARVIS_SKIP_CLAP_GATE</Name><Value>1</Value>
  </EnvironmentVariable>
  <EnvironmentVariable>
    <Name>JARVIS_WAKE_WORD_ONLY</Name><Value>1</Value>
  </EnvironmentVariable>
  <EnvironmentVariable>
    <Name>PYTHONUTF8</Name><Value>1</Value>
  </EnvironmentVariable>
</EnvironmentVariables>
"@

# Register the task (overwrite if exists)
Write-Host "📋 Registering Task Scheduler task: '$TaskName'..." -ForegroundColor Cyan

try {
    # Remove existing task silently
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Force `
        -ErrorAction Stop | Out-Null

    Write-Host ""
    Write-Host "✅ JARVIS auto-start installed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Task Name : $TaskName" -ForegroundColor White
    Write-Host "  Trigger   : At logon ($($env:USERNAME))" -ForegroundColor White
    Write-Host "  Mode      : Background, wake-word listening" -ForegroundColor White
    Write-Host "  Activation: Say 'Hey JARVIS' after login" -ForegroundColor White
    Write-Host ""
    Write-Host "To remove auto-start, run:" -ForegroundColor DarkGray
    Write-Host "  .\startup\install_autostart.ps1 -Uninstall" -ForegroundColor DarkGray
    Write-Host ""
} catch {
    Write-Host "❌ Failed to register task: $_" -ForegroundColor Red
    Write-Host "   Make sure you are running PowerShell as Administrator." -ForegroundColor Red
    exit 1
}
