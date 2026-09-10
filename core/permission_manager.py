"""Permission and Security Manager for JARVIS-OS-V2.

Provides legitimate permission evaluation, error classification (Categories A-M),
Windows UAC elevation helpers, and permission state caching.
Never silently bypasses OS security, MFA, CAPTCHA, or authentication.
"""

from __future__ import annotations

import ctypes
import os
import platform
import string
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.tool_result import ErrorCategory, ToolResult

_IS_WINDOWS = platform.system() == "Windows"


@dataclass
class PermissionState:
    granted_paths: set[str] = field(default_factory=set)
    elevation_confirmed: bool = False


_state = PermissionState()


def is_admin() -> bool:
    """Check if the current Python process is running with Administrator privileges."""
    if _IS_WINDOWS:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    else:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False


def get_available_windows_drives() -> list[Path]:
    """Return all accessible drive roots on Windows (e.g. C:\\, D:\\)."""
    drives: list[Path] = []
    if not _IS_WINDOWS:
        return [Path("/")]

    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive_path = Path(f"{letter}:\\")
                if drive_path.exists():
                    drives.append(drive_path)
            bitmask >>= 1
    except Exception:
        # Fallback to common letters
        for letter in ("C", "D", "E", "F", "Z"):
            p = Path(f"{letter}:\\")
            if p.exists():
                drives.append(p)

    return drives or [Path("C:\\")]


def get_safe_roots() -> list[Path]:
    """Return all directories accessible by the user's account."""
    roots: list[Path] = []

    # User directories
    home = Path.home()
    roots.append(home)
    for sub in ("Desktop", "Downloads", "Documents", "Pictures", "Music", "Videos"):
        p = home / sub
        if p.exists():
            roots.append(p)

    # Current working directory & repository base
    try:
        cwd = Path.cwd().resolve()
        roots.append(cwd)
    except Exception:
        pass

    # Windows logical drives
    if _IS_WINDOWS:
        for drive in get_available_windows_drives():
            roots.append(drive)

    # Dedup
    seen = set()
    unique_roots = []
    for r in roots:
        res = str(r.resolve()).lower() if r.exists() else str(r).lower()
        if res not in seen:
            seen.add(res)
            unique_roots.append(r)

    return unique_roots


def is_path_accessible(target: Path, mode: str = "r") -> tuple[bool, str]:
    """Verify whether a path can legitimately be accessed by current user."""
    try:
        resolved = target.resolve()
    except Exception as e:
        return False, f"Invalid path {target}: {e}"

    # Check cached approval
    if str(resolved) in _state.granted_paths:
        return True, "Permission previously granted."

    # Check safe roots
    safe_roots = get_safe_roots()
    is_in_root = any(
        resolved == r.resolve() or resolved.is_relative_to(r.resolve())
        for r in safe_roots
        if r.exists()
    )

    if not is_in_root:
        return False, f"Path '{target}' is outside accessible roots."

    # Test actual OS permissions
    if resolved.exists():
        if mode in ("r", "read") and not os.access(resolved, os.R_OK):
            return False, f"OS read permission denied for '{target}'."
        if mode in ("w", "write") and not os.access(resolved, os.W_OK):
            return False, f"OS write permission denied for '{target}'."
        if mode in ("x", "exec") and not os.access(resolved, os.X_OK):
            return False, f"OS execute permission denied for '{target}'."
    else:
        # Check parent directory writable for creation
        parent = resolved.parent
        if parent.exists() and mode in ("w", "write") and not os.access(parent, os.W_OK):
            return False, f"Parent directory '{parent}' is not writable."

    return True, "Path is accessible."


def classify_error(exc: Exception | str) -> ErrorCategory:
    """Classify an error into one of the standardized categories (A-M)."""
    text = str(exc).lower()

    if isinstance(exc, FileNotFoundError) or "file not found" in text or "no such file" in text:
        return ErrorCategory.FILE_NOT_FOUND

    if isinstance(exc, PermissionError) or "access denied" in text or "permission denied" in text:
        return ErrorCategory.OS_PERMISSION_DENIED

    if isinstance(exc, TimeoutError) or "timed out" in text or "timeout" in text:
        return ErrorCategory.TOOL_TIMEOUT

    if "captcha" in text or "cloudflare" in text or "turnstile" in text:
        return ErrorCategory.CAPTCHA_OR_MFA_REQUIRED

    if "login required" in text or "authenticate" in text or "unauthorized" in text or "sign in" in text:
        return ErrorCategory.BROWSER_AUTH_REQUIRED

    if "app not found" in text or "is not installed" in text or "executable not found" in text:
        return ErrorCategory.APP_NOT_FOUND

    if "connection refused" in text or "network is unreachable" in text or "dns" in text or "socket" in text:
        return ErrorCategory.NETWORK_FAILURE

    if "temporary" in text or "busy" in text or "locked" in text or "resource temporarily unavailable" in text:
        return ErrorCategory.TEMPORARY_FAILURE

    if "confirm" in text or "approval required" in text or "user action" in text:
        return ErrorCategory.USER_CONFIRMATION_REQUIRED

    if "unknown tool" in text or "not supported in this mode" in text or "unavailable" in text:
        return ErrorCategory.COMMAND_UNDERSTOOD_TOOL_UNAVAILABLE

    return ErrorCategory.TOOL_EXECUTION_FAILED


def request_windows_elevation(cmd: str, params: str = "") -> ToolResult:
    """Request legitimate Windows Administrator elevation through ShellExecute runas."""
    if not _IS_WINDOWS:
        return ToolResult.fail(
            "Elevation is only supported on Windows.",
            error_type=ErrorCategory.OS_PERMISSION_DENIED,
        )

    if is_admin():
        return ToolResult.ok("Already running with Administrator privileges.")

    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            cmd,
            params,
            None,
            1,  # SW_SHOWNORMAL
        )
        # ShellExecute returns > 32 on success
        if int(ret) > 32:
            _state.elevation_confirmed = True
            return ToolResult.ok(
                f"Elevation prompt approved. Process launched as Administrator: {cmd}",
                data={"returncode": ret},
            )
        elif int(ret) == 1223:  # ERROR_CANCELLED (User cancelled UAC)
            return ToolResult.waiting_for_user(
                "Administrator approval was declined by user at the UAC prompt.",
                error_type=ErrorCategory.USER_CONFIRMATION_REQUIRED,
            )
        else:
            return ToolResult.fail(
                f"Elevation request failed with code {ret}.",
                error_type=ErrorCategory.OS_PERMISSION_DENIED,
            )
    except Exception as e:
        return ToolResult.fail(
            f"Could not request elevation: {e}",
            error_type=ErrorCategory.OS_PERMISSION_DENIED,
        )
