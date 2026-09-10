"""
Platform detection utilities: Identify running platform and provide
platform-specific implementations.

Supports:
  - Windows (win32)
  - macOS (darwin)
  - Linux (linux)
  - Web/Browser (browser)
  - iOS (ios)
  - Android (android)
"""

from __future__ import annotations

import platform
import os
import sys
from typing import Literal
from pathlib import Path


# Platform type literals
PlatformName = Literal["windows", "macos", "linux", "web", "ios", "android"]


class PlatformDetector:
    """Detects and caches the current platform."""

    _platform: PlatformName | None = None

    @classmethod
    def get_platform(cls) -> PlatformName:
        """Detect and return the current platform."""
        if cls._platform is not None:
            return cls._platform

        # Check environment variable first (useful for testing/containers)
        env_platform = os.environ.get("JARVIS_PLATFORM", "").lower()
        if env_platform in ("windows", "macos", "linux", "web", "ios", "android"):
            cls._platform = env_platform  # type: ignore
            return cls._platform  # type: ignore

        # Detect from sys.platform
        system = platform.system().lower()

        if system == "windows" or sys.platform == "win32":
            cls._platform = "windows"
        elif system == "darwin" or sys.platform == "darwin":
            cls._platform = "macos"
        elif system == "linux" or sys.platform == "linux":
            cls._platform = "linux"
        else:
            # Fallback
            cls._platform = "linux"

        return cls._platform

    @classmethod
    def is_windows(cls) -> bool:
        return cls.get_platform() == "windows"

    @classmethod
    def is_macos(cls) -> bool:
        return cls.get_platform() == "macos"

    @classmethod
    def is_linux(cls) -> bool:
        return cls.get_platform() == "linux"

    @classmethod
    def is_desktop(cls) -> bool:
        """True if running on desktop (Windows, macOS, Linux)."""
        return cls.get_platform() in ("windows", "macos", "linux")

    @classmethod
    def is_mobile(cls) -> bool:
        """True if running on mobile (iOS, Android)."""
        return cls.get_platform() in ("ios", "android")

    @classmethod
    def is_web(cls) -> bool:
        """True if running in browser."""
        return cls.get_platform() == "web"


class PlatformPaths:
    """Platform-specific directory locations."""

    @staticmethod
    def get_config_dir() -> Path:
        """Get platform-specific config directory."""
        platform_name = PlatformDetector.get_platform()

        if platform_name == "windows":
            base = Path(os.environ.get("APPDATA", "")) or Path.home() / "AppData" / "Roaming"
            return base / "JARVIS"

        if platform_name == "macos":
            return Path.home() / "Library" / "Application Support" / "JARVIS"

        # Linux and others
        base = os.environ.get("XDG_CONFIG_HOME")
        if base:
            return Path(base) / "jarvis"
        return Path.home() / ".config" / "jarvis"

    @staticmethod
    def get_data_dir() -> Path:
        """Get platform-specific data directory."""
        platform_name = PlatformDetector.get_platform()

        if platform_name == "windows":
            base = Path(os.environ.get("APPDATA", "")) or Path.home() / "AppData" / "Roaming"
            return base / "JARVIS" / "data"

        if platform_name == "macos":
            return Path.home() / "Library" / "Application Support" / "JARVIS"

        # Linux and others
        base = os.environ.get("XDG_DATA_HOME")
        if base:
            return Path(base) / "jarvis"
        return Path.home() / ".local" / "share" / "jarvis"

    @staticmethod
    def get_cache_dir() -> Path:
        """Get platform-specific cache directory."""
        platform_name = PlatformDetector.get_platform()

        if platform_name == "windows":
            base = Path(os.environ.get("LOCALAPPDATA", "")) or Path.home() / "AppData" / "Local"
            return base / "JARVIS" / "Cache"

        if platform_name == "macos":
            return Path.home() / "Library" / "Caches" / "JARVIS"

        # Linux and others
        base = os.environ.get("XDG_CACHE_HOME")
        if base:
            return Path(base) / "jarvis"
        return Path.home() / ".cache" / "jarvis"

    @staticmethod
    def get_logs_dir() -> Path:
        """Get platform-specific logs directory."""
        if PlatformDetector.is_windows():
            return PlatformPaths.get_config_dir() / "logs"

        if PlatformDetector.is_macos():
            return Path.home() / "Library" / "Logs" / "JARVIS"

        # Linux
        return PlatformPaths.get_data_dir() / "logs"


class PlatformShell:
    """Platform-specific shell command execution."""

    @staticmethod
    def open_file(path: str) -> bool:
        """Open a file with the default application."""
        import subprocess

        try:
            if PlatformDetector.is_windows():
                os.startfile(path)  # type: ignore
            elif PlatformDetector.is_macos():
                subprocess.run(["open", path], check=True)
            else:
                # Linux
                subprocess.run(["xdg-open", path], check=True)
            return True
        except Exception:
            return False

    @staticmethod
    def open_url(url: str) -> bool:
        """Open a URL in the default browser."""
        import subprocess

        try:
            if PlatformDetector.is_windows():
                os.startfile(url)  # type: ignore
            elif PlatformDetector.is_macos():
                subprocess.run(["open", url], check=True)
            else:
                subprocess.run(["xdg-open", url], check=True)
            return True
        except Exception:
            return False

    @staticmethod
    def get_clipboard() -> str | None:
        """Get text from system clipboard."""
        try:
            if PlatformDetector.is_windows():
                import tkinter
                root = tkinter.Tk()
                root.withdraw()
                text = root.clipboard_get()
                root.destroy()
                return text
            elif PlatformDetector.is_macos():
                import subprocess
                result = subprocess.run(
                    ["pbpaste"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                return result.stdout.strip()
            else:
                # Linux - try xclip first, then xsel
                import subprocess
                try:
                    result = subprocess.run(
                        ["xclip", "-selection", "clipboard", "-o"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    return result.stdout.strip()
                except Exception:
                    result = subprocess.run(
                        ["xsel", "-b"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    return result.stdout.strip()
        except Exception:
            return None

    @staticmethod
    def set_clipboard(text: str) -> bool:
        """Set text to system clipboard."""
        try:
            if PlatformDetector.is_windows():
                import tkinter
                root = tkinter.Tk()
                root.withdraw()
                root.clipboard_clear()
                root.clipboard_append(text)
                root.update()
                root.destroy()
                return True
            elif PlatformDetector.is_macos():
                import subprocess
                subprocess.run(
                    ["pbcopy"],
                    input=text.encode("utf-8"),
                    check=True,
                )
                return True
            else:
                # Linux
                import subprocess
                try:
                    subprocess.run(
                        ["xclip", "-selection", "clipboard"],
                        input=text.encode("utf-8"),
                        check=True,
                    )
                    return True
                except Exception:
                    subprocess.run(
                        ["xsel", "-b"],
                        input=text.encode("utf-8"),
                        check=True,
                    )
                    return True
        except Exception:
            return False


class PlatformNotifications:
    """Platform-specific notification system."""

    @staticmethod
    def show_notification(title: str, message: str, urgency: str = "normal") -> bool:
        """Show a system notification."""
        try:
            if PlatformDetector.is_windows():
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=5)
                return True

            elif PlatformDetector.is_macos():
                import subprocess
                script = f'display notification "{message}" with title "{title}"'
                subprocess.run(["osascript", "-e", script], check=True)
                return True

            else:
                # Linux - use notify-send
                import subprocess
                priority_map = {"low": "low", "normal": "normal", "urgent": "critical"}
                priority = priority_map.get(urgency, "normal")
                subprocess.run(
                    ["notify-send", "-u", priority, title, message],
                    check=True,
                )
                return True
        except Exception:
            return False


class PlatformInfo:
    """Get platform-specific system information."""

    @staticmethod
    def get_info() -> dict:
        """Get comprehensive platform information."""
        import psutil
        import os

        platform_name = PlatformDetector.get_platform()

        return {
            "platform": platform_name,
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "cpu_count": psutil.cpu_count(logical=False),
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "total_memory_gb": psutil.virtual_memory().total / (1024**3),
            "available_memory_gb": psutil.virtual_memory().available / (1024**3),
            "disk_usage_percent": psutil.disk_usage("/").percent,
        }
