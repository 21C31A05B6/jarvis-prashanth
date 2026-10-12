"""Todo List and Task Scheduler for JARVIS OS.

Manages persistent tasks, todos, and schedules.
- Saves tasks to memory/todo_schedule.json.
- Runs tasks at the scheduled time even if JARVIS or user is offline (via Windows Task Scheduler).
- If user is online: directly speaks to the user using voice/TTS and displays desktop notification.
- If user is offline: automatically dispatches an email to prashanthpogula24@gmail.com with task instructions.
- If a task is configured to run until done ("until and unless it can do the task"), it keeps retrying,
  alerting, and tracking until explicitly completed.
"""

from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import ctypes
import json
import os
import platform
import re
import smtplib
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Callable, Optional

# Ensure project root is on sys.path
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_BASE_DIR = _base_dir()
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

def _load_env_vars():
    try:
        from dotenv import load_dotenv
        load_dotenv(_BASE_DIR / ".env")
    except Exception:
        pass
    env_file = _BASE_DIR / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass

_load_env_vars()

TODO_STORAGE_PATH = _BASE_DIR / "memory" / "todo_schedule.json"
DEFAULT_EMAIL_RECIPIENT = "prashanthpogula24@gmail.com"
_STORAGE_LOCK = threading.RLock()
_SYSTEM = platform.system()


# ---------------------------------------------------------------------------
# Storage & Persistence
# ---------------------------------------------------------------------------

def _load_tasks_raw() -> list[dict]:
    with _STORAGE_LOCK:
        if not TODO_STORAGE_PATH.exists():
            return []
        try:
            content = TODO_STORAGE_PATH.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "tasks" in data:
                return data["tasks"]
            return []
        except Exception as exc:
            print(f"[TodoScheduler] [WARN] Error reading {TODO_STORAGE_PATH}: {exc}")
            return []


def _save_tasks_raw(tasks: list[dict]) -> bool:
    with _STORAGE_LOCK:
        try:
            TODO_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps({"tasks": tasks, "updated_at": datetime.now().isoformat()}, indent=2, ensure_ascii=False)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=TODO_STORAGE_PATH.parent,
                prefix=".todo_schedule.",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_path = Path(tmp.name)
            os.replace(tmp_path, TODO_STORAGE_PATH)
            return True
        except Exception as exc:
            print(f"[TodoScheduler] [ERROR] Failed to save tasks: {exc}")
            return False


# ---------------------------------------------------------------------------
# User Presence (Online vs Offline) Detection
# ---------------------------------------------------------------------------

class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_windows_idle_seconds() -> float:
    """Return user idle duration in seconds on Windows, or 0.0 if unavailable."""
    if _SYSTEM != "Windows":
        return 0.0
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0.0, millis / 1000.0)
    except Exception:
        pass
    return 0.0


def is_workstation_locked() -> bool:
    """Check if the Windows workstation is currently locked."""
    if _SYSTEM != "Windows":
        return False
    try:
        # If GetForegroundWindow returns 0 or user desktop is not active
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd == 0:
            return True
    except Exception:
        pass
    return False


def is_user_online(idle_threshold_seconds: float = 300.0) -> tuple[bool, str]:
    """
    Determines whether the user is physically active at the workstation ('online')
    or away / idle / workstation locked ('offline').
    """
    # 1. Check JARVIS UI / API status
    jarvis_online = False
    try:
        from api.status import read_status
        status = read_status()
        if status.get("state") == "online":
            jarvis_online = True
    except Exception:
        pass

    # 2. Check physical user input on Windows
    if _SYSTEM == "Windows":
        if is_workstation_locked():
            return False, "Workstation is locked (user away/offline)"
        idle_sec = get_windows_idle_seconds()
        if idle_sec > idle_threshold_seconds:
            return False, f"User idle for {int(idle_sec)}s (exceeds {int(idle_threshold_seconds)}s threshold)"
        return True, f"User active at computer (last input {int(idle_sec)}s ago)"

    # Fallback for non-Windows: consider online if JARVIS is running
    if jarvis_online:
        return True, "JARVIS process is active"
    return False, "No active user session detected"


# ---------------------------------------------------------------------------
# Direct Voice & Notification Output (Online Delivery)
# ---------------------------------------------------------------------------

def speak_direct(message: str, player=None, speak_fn: Optional[Callable[[str], None]] = None) -> bool:
    """
    Directly speak aloud to the user using:
    1) JARVIS live speech session if available.
    2) Native Windows SAPI Speech Synthesizer fallback (audible even when JARVIS stream is idle).
    3) UI subtitles and desktop toast notifications.
    """
    clean_text = message.replace('"', '').replace("'", "").replace("\n", " ").strip()
    spoken = False

    # 1. Live session speak
    if speak_fn:
        try:
            speak_fn(clean_text)
            spoken = True
        except Exception as exc:
            print(f"[TodoScheduler] Live speak failed: {exc}")

    # 2. UI logging & subtitles
    if player:
        try:
            if hasattr(player, "write_log"):
                player.write_log(f"[TASK ALERT] {clean_text}")
            if hasattr(player, "show_subtitle"):
                player.show_subtitle(f"TASK // {clean_text.upper()}")
        except Exception:
            pass

    # 3. Windows Native SAPI Voice (Speaks out loud through PC speakers)
    if _SYSTEM == "Windows":
        try:
            # Use PowerShell SAPI to speak asynchronously without blocking
            ps_script = (
                f"$voice = New-Object -ComObject SAPI.SpVoice; "
                f"$voice.Rate = 0; "
                f"$voice.Speak('{clean_text}')"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            spoken = True
        except Exception as exc:
            print(f"[TodoScheduler] SAPI speech failed: {exc}")

    # 4. Desktop Notification (Toast)
    try:
        import importlib
        plyer = importlib.import_module("plyer")
        notification = getattr(plyer, "notification", None)
        if notification is not None and hasattr(notification, "notify"):
            notification.notify(
                title="J.A.R.V.I.S Task Alert",
                message=clean_text[:200],
                timeout=15,
            )
    except Exception:
        # Fallback to win10toast or PowerShell toast
        if _SYSTEM == "Windows":
            try:
                ps_toast = (
                    f"[reflection.assembly]::loadwithpartialname('System.Windows.Forms'); "
                    f"$notify = new-object system.windows.forms.notifyicon; "
                    f"$notify.icon = [system.drawing.systemicons]::information; "
                    f"$notify.visible = $true; "
                    f"$notify.showballoontip(10000, 'J.A.R.V.I.S Task Alert', '{clean_text[:150]}', [system.windows.forms.tooltipicon]::Info)"
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_toast],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    return spoken


# ---------------------------------------------------------------------------
# Gmail Dispatch (Offline Delivery)
# ---------------------------------------------------------------------------

def send_task_email(
    task: dict,
    recipient: str = DEFAULT_EMAIL_RECIPIENT,
    custom_subject: str = "",
    player=None
) -> tuple[bool, str]:
    """
    Sends an automated task alert email to the user when they are offline.
    Uses:
    1) Official Gmail API if authorized in JARVIS (via email_control).
    2) Direct SMTP with Gmail if credentials or app password configured.
    """
    title = task.get("title", "Scheduled Task")
    desc = task.get("description", "No extra details provided.")
    due_date = task.get("due_date", "Today")
    due_time = task.get("due_time", "Now")
    task_id = task.get("task_id", "N/A")
    until_done = task.get("until_done", True)
    retries = task.get("retry_count", 0)

    subject = custom_subject or f"[J.A.R.V.I.S Task Notification] {title}"

    body_text = f"""Greetings Sir,

This is an automated priority notification from J.A.R.V.I.S OS.
You are currently away or offline from your workstation.

==================================================
SCHEDULED TASK DETAILS
==================================================
Task: {title}
Scheduled Time: {due_date} at {due_time}
Task ID: {task_id}
Tracking: {"Persistent until completed" if until_done else "One-time notice"}
Attempt Count: {retries + 1}

WHAT YOU NEED TO DO AT THIS TIME:
{desc}

==================================================
JARVIS status:
JARVIS is actively monitoring this task. Once you have completed it,
you can announce to JARVIS: "Jarvis, mark task '{title}' as completed".

Respectfully,
J.A.R.V.I.S. (Always at your service)
"""

    body_html = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f19; color: #e2e8f0; padding: 24px;">
  <div style="max-width: 580px; margin: auto; background-color: #111827; border: 1px solid #1f2937; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
    <div style="background: linear-gradient(135deg, #0ea5e9, #3b82f6); padding: 20px; color: white;">
      <h2 style="margin: 0; font-size: 20px; letter-spacing: 0.5px;">J.A.R.V.I.S // TASK ALERT</h2>
      <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">Offline Scheduled Notification</p>
    </div>
    <div style="padding: 24px;">
      <p style="font-size: 15px; margin-top: 0;">Greetings Sir,</p>
      <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">You are currently offline from your workstation. Here is what you scheduled to do right now:</p>
      
      <div style="background-color: #1e293b; border-left: 4px solid #0ea5e9; padding: 16px; border-radius: 6px; margin: 20px 0;">
        <h3 style="margin: 0 0 8px 0; color: #38bdf8; font-size: 17px;">{title}</h3>
        <p style="margin: 0 0 12px 0; color: #cbd5e1; font-size: 14px; line-height: 1.5;">{desc}</p>
        <div style="font-size: 12px; color: #64748b;">
          <strong>Scheduled:</strong> {due_date} {due_time} &bull; 
          <strong>Status:</strong> Pending completion
        </div>
      </div>

      <div style="background-color: #0f172a; border: 1px solid #334155; padding: 12px; border-radius: 6px; font-size: 13px; color: #94a3b8;">
        <strong>Persistent Tracking:</strong> JARVIS will keep tracking this task until you confirm it is done.
      </div>
    </div>
    <div style="background-color: #0b0f19; padding: 14px 24px; border-top: 1px solid #1f2937; font-size: 12px; color: #64748b; text-align: right;">
      J.A.R.V.I.S. Operating System
    </div>
  </div>
</body>
</html>
"""

    # 1. Attempt using official Gmail API from email_control
    try:
        from actions.email_control import _send_gmail
        draft = {
            "to": recipient,
            "subject": subject,
            "body": body_text,
        }
        res = _send_gmail(draft)
        if "Email sent through Gmail to" in str(res):
            print(f"[TodoScheduler] [OK] Email dispatched via Gmail API to {recipient}")
            return True, f"Email sent via Gmail API to {recipient}."
    except Exception as exc:
        print(f"[TodoScheduler] [INFO] Gmail API not available: {exc}")

    # 2. Attempt using SMTP (Gmail SMTP with App Password)
    smtp_user = (
        os.environ.get("GMAIL_SENDER")
        or os.environ.get("SMTP_USER")
        or os.environ.get("EMAIL_USER")
        or recipient
    )
    smtp_pass = (
        os.environ.get("GMAIL_APP_PASSWORD")
        or os.environ.get("SMTP_PASSWORD")
        or os.environ.get("EMAIL_PASSWORD")
        or ""
    ).replace(" ", "").strip()

    if smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"JARVIS OS <{smtp_user}>"
            msg["To"] = recipient
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))

            smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
            smtp_port = int(os.environ.get("SMTP_PORT", 587))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [recipient], msg.as_string())

            print(f"[TodoScheduler] [OK] Email dispatched via SMTP to {recipient}")
            return True, f"Email sent via SMTP to {recipient}."
        except Exception as exc:
            print(f"[TodoScheduler] [ERROR] SMTP send failed: {exc}")

    # 3. If no email credentials yet, write to offline notification queue and notify in logs
    offline_queue = _base_dir() / "memory" / "pending_emails.json"
    try:
        pending = []
        if offline_queue.exists():
            pending = json.loads(offline_queue.read_text(encoding="utf-8"))
        pending.append({
            "task_id": task_id,
            "to": recipient,
            "subject": subject,
            "body": body_text,
            "queued_at": datetime.now().isoformat(),
        })
        offline_queue.write_text(json.dumps(pending, indent=2), encoding="utf-8")
    except Exception:
        pass

    return False, (
        f"Email drafted for {recipient}. (To enable automatic sending, connect Gmail OAuth "
        "or set GMAIL_APP_PASSWORD in .env)"
    )


# ---------------------------------------------------------------------------
# Windows Task Scheduler Integration (For Running While Offline)
# ---------------------------------------------------------------------------

def _scripts_dir() -> Path:
    d = Path.home() / ".jarvis" / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def register_os_schedule(task: dict) -> bool:
    """
    Registers a scheduled task in Windows Task Scheduler so it runs at the scheduled time
    even if JARVIS is closed, offline, or system was sleeping.
    """
    if _SYSTEM != "Windows":
        return False

    due_iso = task.get("due_iso")
    if not due_iso:
        return False

    try:
        target_dt = datetime.fromisoformat(due_iso)
    except Exception:
        return False

    if target_dt <= datetime.now():
        return False

    task_id = task["task_id"]
    task_name = f"JARVIS_Task_{task_id}"

    python_exe = Path(sys.executable)
    pythonw = python_exe.parent / "pythonw.exe"
    if pythonw.exists():
        python_exe = pythonw

    xml_path = _scripts_dir() / f"{task_name}.xml"

    xml_content = (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        '  <RegistrationInfo><Description>J.A.R.V.I.S Automated Todo/Schedule Runner</Description></RegistrationInfo>\n'
        '  <Triggers><TimeTrigger>\n'
        f'    <StartBoundary>{target_dt.strftime("%Y-%m-%dT%H:%M:%S")}</StartBoundary>\n'
        '    <Enabled>true</Enabled>\n'
        '  </TimeTrigger></Triggers>\n'
        '  <Actions><Exec>\n'
        f'    <Command>{python_exe}</Command>\n'
        f'    <Arguments>-m actions.todo_scheduler --trigger {task_id}</Arguments>\n'
        f'    <WorkingDirectory>{_BASE_DIR}</WorkingDirectory>\n'
        '  </Exec></Actions>\n'
        '  <Settings>\n'
        '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
        '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
        '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
        '    <StartWhenAvailable>true</StartWhenAvailable>\n'
        '    <ExecutionTimeLimit>PT15M</ExecutionTimeLimit>\n'
        '    <Enabled>true</Enabled>\n'
        '  </Settings>\n'
        '  <Principals><Principal>\n'
        '    <LogonType>InteractiveToken</LogonType>\n'
        '    <RunLevel>LeastPrivilege</RunLevel>\n'
        '  </Principal></Principals>\n'
        '</Task>'
    )

    try:
        xml_path.write_text(xml_content, encoding="utf-16")
        res = subprocess.run(
            ["schtasks", "/Create", "/TN", task_name, "/XML", str(xml_path), "/F"],
            capture_output=True,
            text=True,
        )
        xml_path.unlink(missing_ok=True)
        if res.returncode == 0:
            print(f"[TodoScheduler] [SCHEDULED] Windows task: {task_name}")
            return True
        else:
            print(f"[TodoScheduler] [WARN] schtasks failed: {res.stderr or res.stdout}")
    except Exception as exc:
        print(f"[TodoScheduler] [WARN] Task scheduler registration exception: {exc}")
    return False


def remove_os_schedule(task_id: str) -> None:
    if _SYSTEM != "Windows":
        return
    task_name = f"JARVIS_Task_{task_id}"
    try:
        subprocess.run(
            ["schtasks", "/Delete", "/TN", task_name, "/F"],
            capture_output=True,
            text=True,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Core Task Management Logic & Natural Language Parsing
# ---------------------------------------------------------------------------

def parse_task_string(raw_text: str) -> dict:
    """
    Parses natural language task inputs into structured parameters.
    Handles relative times ('in 15 minutes'), specific times ('at 4:30 PM', 'at 17:00'),
    dates ('tomorrow', 'today', 'on 2026-10-15'), and cleans task prefixes.
    """
    text = (raw_text or "").strip()
    if not text:
        return {"title": "", "due_date": None, "due_time": None, "description": ""}

    # Strip conversational prefixes
    prefixes = (
        r"^(?:please\s+)?(?:remind\s+me\s+to|add\s+to\s+todo|add\s+todo|schedule|create\s+task|task\s*:|todo\s*:)\s*",
    )
    for p in prefixes:
        text = re.sub(p, "", text, flags=re.IGNORECASE).strip()

    now = datetime.now()
    target_dt = None
    due_date = None
    due_time = None

    # 1. Match relative time: "in X minutes/hours/mins"
    rel_match = re.search(r"\bin\s+(\d+)\s*(mins?|minutes?|hours?|hrs?)\b", text, re.IGNORECASE)
    if rel_match:
        qty = int(rel_match.group(1))
        unit = rel_match.group(2).lower()
        if "hour" in unit or "hr" in unit:
            target_dt = now + timedelta(hours=qty)
        else:
            target_dt = now + timedelta(minutes=qty)
        text = text[:rel_match.start()] + text[rel_match.end():]

    # 2. Match date: "tomorrow", "today", "on YYYY-MM-DD"
    if re.search(r"\btomorrow\b", text, re.IGNORECASE):
        target_date_obj = now + timedelta(days=1)
        due_date = target_date_obj.strftime("%Y-%m-%d")
        text = re.sub(r"\btomorrow\b", "", text, flags=re.IGNORECASE)
    elif re.search(r"\btoday\b", text, re.IGNORECASE):
        due_date = now.strftime("%Y-%m-%d")
        text = re.sub(r"\btoday\b", "", text, flags=re.IGNORECASE)
    else:
        date_match = re.search(r"\bon\s+(\d{4}-\d{2}-\d{2})\b", text, re.IGNORECASE)
        if date_match:
            due_date = date_match.group(1)
            text = text[:date_match.start()] + text[date_match.end():]

    # 3. Match specific time: "at 5:30 PM", "at 5pm", "at 17:30", "at 9 am"
    time_match = re.search(r"\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", text, re.IGNORECASE)
    if time_match:
        time_str = time_match.group(1).strip()
        text = text[:time_match.start()] + text[time_match.end():]
        # Normalize time_str
        try:
            # Try formats
            for fmt in ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p", "%H:%M", "%H"):
                try:
                    parsed_t = datetime.strptime(time_str.upper(), fmt).time()
                    due_time = parsed_t.strftime("%H:%M")
                    break
                except ValueError:
                    continue
        except Exception:
            pass

    if target_dt:
        due_date = target_dt.strftime("%Y-%m-%d")
        due_time = target_dt.strftime("%H:%M")
    elif due_time and not due_date:
        # Check if due_time today has passed
        try:
            t_obj = datetime.strptime(due_time, "%H:%M").time()
            dt_today = datetime.combine(now.date(), t_obj)
            if dt_today <= now:
                due_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                due_date = now.strftime("%Y-%m-%d")
        except Exception:
            due_date = now.strftime("%Y-%m-%d")
    elif not due_time:
        due_date = due_date or now.strftime("%Y-%m-%d")
        due_time = now.strftime("%H:%M")

    # Clean up leftover whitespace / punctuation from title
    clean_title = re.sub(r"\s+", " ", text).strip(" ,.-;:")
    if not clean_title:
        clean_title = "Scheduled Task"

    return {
        "title": clean_title,
        "due_date": due_date,
        "due_time": due_time,
        "description": f"Scheduled task: {clean_title}",
    }


def add_task_from_text(raw_text: str, until_done: bool = True) -> dict:
    """Convenience function to parse a raw text string and add it to the schedule."""
    parsed = parse_task_string(raw_text)
    return add_task(
        title=parsed["title"],
        description=parsed.get("description") or f"Task: {parsed['title']}",
        due_date=parsed.get("due_date"),
        due_time=parsed.get("due_time"),
        until_done=until_done,
    )


def add_task(
    title: str,
    description: str = "",
    due_date: Optional[str] = None,
    due_time: Optional[str] = None,
    until_done: bool = True,
    action_type: str = "reminder",
    command: str = "",
    retry_interval_minutes: int = 15,
    email_recipient: str = DEFAULT_EMAIL_RECIPIENT,
) -> dict:
    """
    Creates a new task or schedule.
    Saves to memory/todo_schedule.json and registers Windows Task Scheduler if a future due time is given.
    """
    now = datetime.now()
    task_id = f"todo_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(2).hex()}"

    due_iso = None
    if due_date and due_time:
        try:
            dt = datetime.strptime(f"{due_date} {due_time}", "%Y-%m-%d %H:%M")
            due_iso = dt.isoformat()
        except Exception:
            pass
    elif due_time and not due_date:
        # Default to today (or tomorrow if time already passed)
        try:
            today_str = now.strftime("%Y-%m-%d")
            dt = datetime.strptime(f"{today_str} {due_time}", "%Y-%m-%d %H:%M")
            if dt <= now:
                dt += timedelta(days=1)
            due_date = dt.strftime("%Y-%m-%d")
            due_iso = dt.isoformat()
        except Exception:
            pass

    task = {
        "task_id": task_id,
        "title": title.strip(),
        "description": description.strip(),
        "action_type": action_type,
        "command": command.strip(),
        "due_date": due_date or now.strftime("%Y-%m-%d"),
        "due_time": due_time or now.strftime("%H:%M"),
        "due_iso": due_iso or now.isoformat(),
        "status": "pending",
        "until_done": bool(until_done),
        "retry_interval_minutes": max(1, int(retry_interval_minutes)),
        "retry_count": 0,
        "max_retries": 100,
        "email_recipient": email_recipient.strip() or DEFAULT_EMAIL_RECIPIENT,
        "created_at": now.isoformat(),
        "last_run_at": None,
        "completed_at": None,
        "last_notification_mode": None,
        "history": [f"{now.strftime('%Y-%m-%d %H:%M:%S')} Created"],
    }

    tasks = _load_tasks_raw()
    tasks.append(task)
    _save_tasks_raw(tasks)

    # Register OS scheduler
    if due_iso:
        register_os_schedule(task)

    # Log in task history
    try:
        from memory.task_history import record_task
        record_task(task_id, f"Todo/Schedule: {title}", "pending", "Task registered in schedule", "")
    except Exception:
        pass

    return task


def list_tasks(status: str = "open") -> list[dict]:
    """
    Lists tasks filtered by status.
    status: 'open' (pending or in_progress), 'completed', 'all'
    """
    tasks = _load_tasks_raw()
    if status == "open":
        return [t for t in tasks if t.get("status") in ("pending", "in_progress")]
    if status == "completed":
        return [t for t in tasks if t.get("status") == "completed"]
    return tasks


def complete_task(task_id_or_title: str) -> Optional[dict]:
    """
    Marks a task as completed and removes any recurring Windows Task Scheduler task.
    """
    tasks = _load_tasks_raw()
    target = None
    query = task_id_or_title.strip().lower()

    for t in tasks:
        if t["task_id"].lower() == query or query in t["title"].lower():
            target = t
            break

    if not target:
        return None

    target["status"] = "completed"
    target["completed_at"] = datetime.now().isoformat()
    target["history"].append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Marked completed")
    _save_tasks_raw(tasks)

    # Remove any registered scheduled task in OS
    remove_os_schedule(target["task_id"])

    # Update task history
    try:
        from memory.task_history import record_task
        record_task(target["task_id"], f"Todo: {target['title']}", "completed", "Task marked completed", "")
    except Exception:
        pass

    return target


def delete_task(task_id_or_title: str) -> bool:
    """Deletes a task by ID or title match."""
    tasks = _load_tasks_raw()
    query = task_id_or_title.strip().lower()
    initial_len = len(tasks)
    remaining = []
    deleted_id = None

    for t in tasks:
        if t["task_id"].lower() == query or query in t["title"].lower():
            deleted_id = t["task_id"]
            continue
        remaining.append(t)

    if len(remaining) < initial_len:
        _save_tasks_raw(remaining)
        if deleted_id:
            remove_os_schedule(deleted_id)
        return True
    return False


# ---------------------------------------------------------------------------
# Task Execution & Retry Loop ("until and unless it can do the task")
# ---------------------------------------------------------------------------

def execute_or_notify_task(
    task_id: str,
    player=None,
    speak_fn: Optional[Callable[[str], None]] = None,
    force: bool = False,
) -> dict:
    """
    Core executor:
    1. Evaluates if user is online or offline.
    2. If online: speaks directly to user, pops up toast, and announces the task.
    3. If offline: emails prashanthpogula24@gmail.com with task instructions.
    4. If until_done=True and task is not yet completed:
       Keeps task in_progress, increments retry_count, and reschedules next trigger!
    """
    tasks = _load_tasks_raw()
    task = None
    for t in tasks:
        if t["task_id"] == task_id:
            task = t
            break

    if not task:
        return {"success": False, "error": f"Task {task_id} not found"}

    if task.get("status") == "completed" and not force:
        return {"success": True, "message": "Task already completed"}

    now = datetime.now()
    online, presence_reason = is_user_online()
    result_info = {}

    title = task["title"]
    desc = task.get("description", "")
    recipient = task.get("email_recipient", DEFAULT_EMAIL_RECIPIENT)

    # If action_type == "execute" and command is given, run the command
    if task.get("action_type") == "execute" and task.get("command"):
        try:
            cmd = task["command"]
            print(f"[TodoScheduler] [EXEC] Executing automated command: {cmd}")
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            if proc.returncode == 0:
                task["status"] = "completed"
                task["completed_at"] = now.isoformat()
                output_summary = (proc.stdout or "Command finished successfully").strip()[:300]
                task["history"].append(f"{now.strftime('%Y-%m-%d %H:%M:%S')} Command executed: {output_summary}")
                _save_tasks_raw(tasks)
                remove_os_schedule(task_id)

                announcement = f"Sir, I have successfully executed your task: {title}."
                if online:
                    speak_direct(announcement, player=player, speak_fn=speak_fn)
                else:
                    send_task_email(task, recipient=recipient, custom_subject=f"[J.A.R.V.I.S Task Completed] {title}")

                return {"success": True, "completed": True, "message": announcement}
            else:
                err_msg = (proc.stderr or proc.stdout).strip()[:300]
                task["history"].append(f"{now.strftime('%Y-%m-%d %H:%M:%S')} Command failed: {err_msg}")
        except Exception as exc:
            task["history"].append(f"{now.strftime('%Y-%m-%d %H:%M:%S')} Execution error: {exc}")

    # Standard Reminder / Action Check
    if online:
        # User is ONLINE: directly say to user
        spoken_msg = f"Sir, it is time for your scheduled task: {title}. {desc}".strip()
        speak_direct(spoken_msg, player=player, speak_fn=speak_fn)
        task["last_notification_mode"] = "spoken"
        task["history"].append(f"{now.strftime('%Y-%m-%d %H:%M:%S')} Spoken directly to user ({presence_reason})")
        result_info["mode"] = "spoken"
        result_info["message"] = f"Spoken directly to user: {spoken_msg}"
    else:
        # User is OFFLINE: send email to prashanthpogula24@gmail.com
        ok, email_msg = send_task_email(task, recipient=recipient, player=player)
        task["last_notification_mode"] = "emailed"
        task["history"].append(f"{now.strftime('%Y-%m-%d %H:%M:%S')} Emailed to {recipient} ({presence_reason})")
        result_info["mode"] = "emailed"
        result_info["message"] = f"Dispatched email to {recipient}: {email_msg}"

    task["last_run_at"] = now.isoformat()
    task["retry_count"] = task.get("retry_count", 0) + 1

    # If until_done is True and task is not completed, reschedule retry!
    if task.get("until_done") and task.get("status") != "completed":
        task["status"] = "in_progress"
        interval = task.get("retry_interval_minutes", 15)
        next_dt = now + timedelta(minutes=interval)
        task["due_date"] = next_dt.strftime("%Y-%m-%d")
        task["due_time"] = next_dt.strftime("%H:%M")
        task["due_iso"] = next_dt.isoformat()
        task["history"].append(f"Rescheduled retry #{task['retry_count']} for {next_dt.strftime('%H:%M')}")

        # Register next Windows scheduled task
        register_os_schedule(task)
        result_info["rescheduled_for"] = next_dt.strftime("%Y-%m-%d %H:%M")
    else:
        remove_os_schedule(task_id)

    _save_tasks_raw(tasks)
    return {"success": True, **result_info}


def check_and_run_due_tasks(player=None, speak_fn: Optional[Callable[[str], None]] = None) -> list[dict]:
    """
    Checks all pending and in-progress tasks.
    Runs any task whose due time has arrived.
    """
    now = datetime.now()
    tasks = _load_tasks_raw()
    executed = []

    for task in tasks:
        if task.get("status") in ("pending", "in_progress"):
            due_iso = task.get("due_iso")
            if due_iso:
                try:
                    due_dt = datetime.fromisoformat(due_iso)
                    if due_dt <= now:
                        res = execute_or_notify_task(task["task_id"], player=player, speak_fn=speak_fn)
                        executed.append({"task_id": task["task_id"], "title": task["title"], "result": res})
                except Exception as exc:
                    print(f"[TodoScheduler] Error checking task {task.get('task_id')}: {exc}")

    return executed


# ---------------------------------------------------------------------------
# Background Daemon Loop (for active JARVIS sessions)
# ---------------------------------------------------------------------------

_DAEMON_THREAD: Optional[threading.Thread] = None
_DAEMON_RUNNING = False

def start_scheduler_daemon(player=None, speak_fn=None, interval_seconds: int = 30):
    global _DAEMON_THREAD, _DAEMON_RUNNING
    if _DAEMON_RUNNING:
        return
    _DAEMON_RUNNING = True

    def _loop():
        print("[TodoScheduler] [LOOP] Background task scheduler loop started.")
        while _DAEMON_RUNNING:
            try:
                check_and_run_due_tasks(player=player, speak_fn=speak_fn)
            except Exception as exc:
                print(f"[TodoScheduler] Daemon cycle error: {exc}")
            time.sleep(interval_seconds)

    _DAEMON_THREAD = threading.Thread(target=_loop, daemon=True, name="TodoSchedulerDaemon")
    _DAEMON_THREAD.start()


def stop_scheduler_daemon():
    global _DAEMON_RUNNING
    _DAEMON_RUNNING = False


# ---------------------------------------------------------------------------
# Main Action Dispatcher for Gemini Tool Calls
# ---------------------------------------------------------------------------

def todo_scheduler(
    parameters: dict | None = None,
    response=None,
    player=None,
    speak=None,
    session_memory=None,
) -> str:
    """
    Main tool handler for JARVIS.
    """
    params = parameters or {}
    action = str(params.get("action", "list")).strip().lower().replace("-", "_").replace(" ", "_")

    if action in ("add", "create", "schedule"):
        title = str(params.get("title", "")).strip()
        if not title:
            # Fallback to message or task
            title = str(params.get("task", "") or params.get("message", "")).strip()
        if not title:
            return "Please provide a task title or description to add to your todo list."

        description = str(params.get("description", "")).strip()
        due_date = params.get("due_date", "") or params.get("date", "")
        due_time = params.get("due_time", "") or params.get("time", "")
        until_done = params.get("until_done", True)
        action_type = params.get("action_type", "reminder")
        command = params.get("command", "")
        retry_interval = int(params.get("retry_interval_minutes", 15))
        email = str(params.get("email", DEFAULT_EMAIL_RECIPIENT)).strip() or DEFAULT_EMAIL_RECIPIENT

        task = add_task(
            title=title,
            description=description,
            due_date=str(due_date).strip() if due_date else None,
            due_time=str(due_time).strip() if due_time else None,
            until_done=until_done,
            action_type=action_type,
            command=command,
            retry_interval_minutes=retry_interval,
            email_recipient=email,
        )

        schedule_msg = f"scheduled for {task['due_date']} at {task['due_time']}" if due_date or due_time else "added to your active list"
        persistence_msg = "I will keep tracking and alerting until it is completed." if until_done else "Single alert."
        offline_msg = f"If you are online, I will announce it to you directly; if you are offline, I will email {email}."

        return (
            f"Task '{title}' has been {schedule_msg}. {persistence_msg}\n"
            f"{offline_msg} (Task ID: {task['task_id']})"
        )

    elif action in ("list", "show", "view", "get"):
        filter_status = str(params.get("status", "open")).lower()
        tasks = list_tasks(status=filter_status)
        if not tasks:
            return "Your todo and schedule list is currently empty."

        lines = [f"📋 JARVIS Todo & Schedule List ({len(tasks)} tasks):"]
        for i, t in enumerate(tasks, 1):
            status_symbol = "✅" if t.get("status") == "completed" else "⏳"
            until = " [Repeats until done]" if t.get("until_done") else ""
            lines.append(
                f"{i}. {status_symbol} [{t.get('status', 'pending').upper()}] {t['title']} "
                f"(Due: {t.get('due_date')} {t.get('due_time')}){until} - ID: {t['task_id']}"
            )
            if t.get("description"):
                lines.append(f"   Note: {t['description']}")
        return "\n".join(lines)

    elif action in ("complete", "done", "mark_done"):
        task_id = str(params.get("task_id", "") or params.get("title", "")).strip()
        if not task_id:
            return "Please specify which task you have completed."

        completed = complete_task(task_id)
        if completed:
            return f"Excellent, Sir. Task '{completed['title']}' has been marked completed."
        return f"Could not find a task matching '{task_id}'."

    elif action in ("delete", "remove", "cancel"):
        task_id = str(params.get("task_id", "") or params.get("title", "")).strip()
        if not task_id:
            return "Please specify which task to remove."
        if delete_task(task_id):
            return f"Task '{task_id}' has been removed from your list."
        return f"Could not find a task matching '{task_id}'."

    elif action in ("run", "trigger", "execute_now"):
        task_id = str(params.get("task_id", "")).strip()
        if not task_id:
            # Run all due tasks
            executed = check_and_run_due_tasks(player=player, speak_fn=speak)
            return f"Checked and processed {len(executed)} due task(s)."
        res = execute_or_notify_task(task_id, player=player, speak_fn=speak, force=True)
        return f"Task execution result: {res.get('message', res)}"

    elif action in ("gui", "open_gui", "show_gui", "dialog", "window", "textbox"):
        try:
            from actions.todo_dialog import open_todo_window
            threading.Thread(target=open_todo_window, daemon=True).start()
            return "Opening J.A.R.V.I.S To-Do & Task Scheduler input box, Sir."
        except Exception as exc:
            return f"Could not launch To-Do window: {exc}"

    elif action == "status":
        online, reason = is_user_online()
        tasks = list_tasks("open")
        return (
            f"User Presence: {'ONLINE (Direct Voice & Desktop Active)' if online else 'OFFLINE (Email Mode: ' + DEFAULT_EMAIL_RECIPIENT + ')'}\n"
            f"Reason: {reason}\n"
            f"Active open tasks: {len(tasks)}"
        )

    return "Available actions: add, list, complete, delete, run, status, gui."


# ---------------------------------------------------------------------------
# CLI Entrypoint (Used by Windows Task Scheduler when Offline)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS Todo Scheduler CLI")
    parser.add_argument("--trigger", type=str, help="Trigger a specific task by ID")
    parser.add_argument("--check-all", action="store_true", help="Check and trigger all due tasks")
    parser.add_argument("--status", action="store_true", help="Print user online/offline status")
    parser.add_argument("--gui", action="store_true", help="Launch interactive To-Do GUI window")
    args = parser.parse_args()

    if args.gui:
        from actions.todo_dialog import open_todo_window
        open_todo_window()
    elif args.status:
        online, reason = is_user_online()
        print(f"Status: {'ONLINE' if online else 'OFFLINE'} ({reason})")
    elif args.trigger:
        print(f"[TodoScheduler CLI] Triggering task: {args.trigger}")
        res = execute_or_notify_task(args.trigger, force=False)
        print(f"Result: {res}")
    elif args.check_all:
        print("[TodoScheduler CLI] Checking all due tasks...")
        res = check_and_run_due_tasks()
        print(f"Processed: {len(res)} tasks.")
    else:
        parser.print_help()
