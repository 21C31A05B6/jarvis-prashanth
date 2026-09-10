import time
import subprocess
import platform
import shutil
import os

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

from agent.tool_result import ToolResult, ErrorCategory
from core.permission_manager import classify_error

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "gnome-terminal"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
}


_POLITE_PREFIXES = (
    "please open ", "please launch ", "please start ",
    "can you open ", "can you launch ", "can you start ",
    "open up ", "launch ", "start ", "open ",
)

def _normalize(raw: str) -> str:
    # Strip polite/verb prefixes while preserving original casing for the remainder
    cleaned = raw.strip()
    lower = cleaned.lower()
    for prefix in _POLITE_PREFIXES:
        if lower.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            lower = cleaned.lower()
            break

    # Exact alias match
    if lower in _APP_ALIASES:
        return _APP_ALIASES[lower].get(_SYSTEM, cleaned)

    # Substring alias match (alias key fully contained in input)
    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key == lower or alias_key in lower:
            return os_map.get(_SYSTEM, cleaned)

    return cleaned


def _find_windows_app_path(app_name: str) -> str | None:
    if _SYSTEM != "Windows":
        return None
    try:
        import winreg
        keys_to_check = [
            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app_name}",
            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app_name}.exe",
            rf"SOFTWARE\Clients\StartMenuInternet\{app_name}\shell\open\command",
        ]
        for key_path in keys_to_check:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k = winreg.OpenKey(hive, key_path)
                    val, _ = winreg.QueryValueEx(k, "")
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0]
                    if exe and os.path.exists(exe):
                        return exe
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _launch_windows_start_menu_app(app_name: str) -> bool:
    """Launch Microsoft Store apps whose executable is not exposed in PATH."""
    if _SYSTEM != "Windows":
        return False
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    "$app = Get-StartApps -Name "
                    f"'{app_name.replace(chr(39), chr(39) * 2)}' | "
                    "Select-Object -First 1; "
                    "if ($app) { $app.AppID }"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        app_id = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if not app_id:
            return False
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[open_app] Start menu app launch failed: {exc}")
        return False


def _is_app_running(names: list[str]) -> bool:
    if not _PSUTIL:
        return True
    targets = [n.lower().replace(".exe", "").strip() for n in names if n]
    try:
        for p in psutil.process_iter(['name']):
            try:
                pname = (p.info.get('name') or '').lower()
                for t in targets:
                    if t and (t == pname or t in pname or pname.startswith(t)):
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return False


def _launch_windows(app_name: str) -> bool:
    # Store apps such as WhatsApp are commonly not available as executables.
    if app_name.casefold() in {"whatsapp", "telegram", "discord", "slack"}:
        if _launch_windows_start_menu_app(app_name):
            return True

    # 0. Windows registry App Paths
    app_path = _find_windows_app_path(app_name)
    if app_path:
        try:
            subprocess.Popen([app_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"[open_app] direct registry exe launch failed: {e}")

    # 1. Direct path / binary in PATH
    if shutil.which(app_name) or shutil.which(app_name.split(".")[0]):
        try:
            subprocess.Popen(
                app_name,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    # 2. Protocol / URI handler (e.g., ms-settings:, spotify:)
    if ":" in app_name:
        try:
            os.startfile(app_name)
            return True
        except Exception:
            try:
                subprocess.Popen(f'start "" "{app_name}"', shell=True)
                return True
            except Exception:
                pass

    # 3. Fast Windows Shell Start
    try:
        os.startfile(app_name)
        return True
    except Exception:
        pass

    try:
        subprocess.Popen(f'start "" "{app_name}"', shell=True)
        return True
    except Exception:
        pass

    # 4. GUI fallback via Start Menu
    try:
        import pyautogui
        pyautogui.PAUSE = 0.02
        pyautogui.press("win")
        time.sleep(0.15)
        pyautogui.write(app_name, interval=0.0)
        time.sleep(0.15)
        pyautogui.press("enter")
        return True
    except Exception as e:
        print(f"[open_app] Start Menu search failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


def _launch_linux(app_name: str) -> bool:

    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            pass

    try:
        subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        pass

    for desktop_name in [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> ToolResult:
    app_name = (parameters or {}).get("app_name", "").strip()

    if not app_name:
        res = ToolResult.fail("No application name provided.", ErrorCategory.COMMAND_UNDERSTOOD_TOOL_UNAVAILABLE)
        if player:
            player.write_log(str(res))
        return res

    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        res = ToolResult.fail(f"Unsupported operating system: {_SYSTEM}", ErrorCategory.COMMAND_UNDERSTOOD_TOOL_UNAVAILABLE)
        if player:
            player.write_log(str(res))
        return res

    normalized = _normalize(app_name)
    print(f"[open_app] Launching: '{app_name}' → '{normalized}' ({_SYSTEM})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    try:
        launched = launcher(normalized)
        if not launched and normalized.lower() != app_name.lower():
            launched = launcher(app_name)

        if launched:
            time.sleep(0.8)
            verified = _is_app_running([normalized, app_name])
            if verified or not _PSUTIL:
                return ToolResult.ok(
                    f"Opened {app_name}.",
                    data={"app": app_name, "normalized": normalized},
                    verification={"running": True, "app": app_name},
                )

        return ToolResult.fail(
            f"Could not confirm that {app_name} launched. It may not be installed.",
            ErrorCategory.APP_NOT_FOUND,
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        cat = classify_error(e)
        return ToolResult.fail(f"Failed to open {app_name}: {e}", cat)
