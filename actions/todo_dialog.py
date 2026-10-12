"""Dedicated To-Do & Schedule Input Window for JARVIS OS.

Provides a fast, beautiful, holographic desktop text box to:
- Enter and schedule to-do tasks and reminders.
- Set due date and time (or auto-parse from natural language).
- If Online: Announces directly via JARVIS voice and desktop alerts.
- If Offline: Automatically dispatches emails to prashanthpogula24@gmail.com.
- Persistently retries and tracks tasks until completed.
"""

from __future__ import annotations

import os
import re
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_BASE_DIR = _base_dir()
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

# Ensure Qt6 DLLs loaded on Windows
try:
    import core.qt_init  # noqa: F401
except Exception:
    pass

from actions.todo_scheduler import (
    DEFAULT_EMAIL_RECIPIENT,
    add_task,
    complete_task,
    delete_task,
    execute_or_notify_task,
    is_user_online,
    list_tasks,
    parse_task_string,
)


def _launch_pyqt_dialog(parent_app=None):
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor, QFont, QIcon
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

    class JarvisTodoDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("J.A.R.V.I.S. — To-Do & Task Scheduler")
            self.setMinimumSize(680, 560)
            self.resize(720, 600)

            # Styling: Iron-Man / JARVIS cyan & obsidian
            self.setStyleSheet("""
                QDialog {
                    background-color: #060b13;
                    color: #d8ecf8;
                    font-family: 'Segoe UI', Arial, sans-serif;
                }
                QLabel {
                    color: #d8ecf8;
                    background: transparent;
                }
                QLineEdit {
                    background-color: #0b1524;
                    color: #ffffff;
                    border: 1px solid #1e3a5f;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 13px;
                }
                QLineEdit:focus {
                    border: 1px solid #00d2ff;
                    background-color: #0f1c30;
                }
                QPushButton {
                    background-color: #0088cc;
                    color: #ffffff;
                    border: 1px solid #00aaff;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #00aaff;
                    border-color: #00d2ff;
                }
                QPushButton:pressed {
                    background-color: #006699;
                }
                QScrollArea {
                    background: transparent;
                    border: 1px solid #14243b;
                    border-radius: 6px;
                }
                QScrollBar:vertical {
                    background: #060b13;
                    width: 8px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #1e3a5f;
                    min-height: 20px;
                    border-radius: 4px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #00d2ff;
                }
            """)

            main_lay = QVBoxLayout(self)
            main_lay.setContentsMargins(20, 20, 20, 20)
            main_lay.setSpacing(14)

            # --- Header ---
            header_layout = QHBoxLayout()
            title_v = QVBoxLayout()
            title_lbl = QLabel("J.A.R.V.I.S  ·  TO-DO MANAGER")
            title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #00d2ff; letter-spacing: 2px;")
            subtitle_lbl = QLabel(
                f"• ONLINE: Direct Voice Announcement  |  • OFFLINE: Email to {DEFAULT_EMAIL_RECIPIENT}"
            )
            subtitle_lbl.setStyleSheet("font-size: 11px; color: #7f9eb2;")
            title_v.addWidget(title_lbl)
            title_v.addWidget(subtitle_lbl)
            header_layout.addLayout(title_v)

            header_layout.addStretch()

            # Status pill
            online, reason = is_user_online()
            status_lbl = QLabel(f"● {'ONLINE' if online else 'OFFLINE'}")
            status_color = "#00ff88" if online else "#ffaa00"
            status_lbl.setStyleSheet(f"""
                color: {status_color};
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border: 1px solid {status_color}55;
                border-radius: 12px;
                background-color: {status_color}15;
            """)
            header_layout.addWidget(status_lbl)
            main_lay.addLayout(header_layout)

            # Divider line
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet("color: #14243b;")
            main_lay.addWidget(line)

            # --- Input Section ---
            input_box = QFrame()
            input_box.setStyleSheet("""
                QFrame {
                    background-color: #091322;
                    border: 1px solid #142844;
                    border-radius: 8px;
                    padding: 10px;
                }
            """)
            ib_lay = QVBoxLayout(input_box)
            ib_lay.setSpacing(10)

            input_lbl = QLabel("ENTER TASK OR SCHEDULE:")
            input_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #00d2ff; letter-spacing: 1px;")
            ib_lay.addWidget(input_lbl)

            entry_row = QHBoxLayout()
            self.task_input = QLineEdit()
            self.task_input.setPlaceholderText("Type a task (e.g. 'Project status review at 5:00 PM', 'Call doctor tomorrow at 10am')...")
            self.task_input.returnPressed.connect(self._add_task_action)
            entry_row.addWidget(self.task_input, stretch=1)

            add_btn = QPushButton("+ ADD TASK")
            add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            add_btn.setStyleSheet("""
                QPushButton {
                    background-color: #00d2ff;
                    color: #060b13;
                    border: 1px solid #70e6ff;
                    border-radius: 6px;
                    font-weight: bold;
                    padding: 9px 18px;
                }
                QPushButton:hover {
                    background-color: #70e6ff;
                }
            """)
            add_btn.clicked.connect(self._add_task_action)
            entry_row.addWidget(add_btn)
            ib_lay.addLayout(entry_row)

            # Options row: Time input & until done checkbox
            opts_row = QHBoxLayout()
            time_lbl = QLabel("Due Time (optional):")
            time_lbl.setStyleSheet("font-size: 11px; color: #7f9eb2;")
            opts_row.addWidget(time_lbl)

            self.time_input = QLineEdit()
            self.time_input.setPlaceholderText("e.g. 17:30 or 5:00 PM (leave blank to auto-detect)")
            self.time_input.setFixedWidth(240)
            opts_row.addWidget(self.time_input)

            opts_row.addSpacing(16)

            self.until_done_chk = QCheckBox("Track persistently until done")
            self.until_done_chk.setChecked(True)
            self.until_done_chk.setStyleSheet("color: #a4c4d9; font-size: 11px;")
            opts_row.addWidget(self.until_done_chk)

            opts_row.addStretch()
            ib_lay.addLayout(opts_row)

            main_lay.addWidget(input_box)

            # Feedback label
            self.feedback_lbl = QLabel("")
            self.feedback_lbl.setStyleSheet("font-size: 11px; color: #00ff88;")
            main_lay.addWidget(self.feedback_lbl)

            # --- Task List Header ---
            list_header = QHBoxLayout()
            list_title = QLabel("CURRENT TASKS & SCHEDULE")
            list_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #00d2ff; letter-spacing: 1px;")
            list_header.addWidget(list_title)
            list_header.addStretch()

            refresh_btn = QPushButton("↺ Refresh")
            refresh_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #7f9eb2;
                    border: 1px solid #1e3a5f;
                    padding: 4px 10px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    color: #00d2ff;
                    border-color: #00d2ff;
                }
            """)
            refresh_btn.clicked.connect(self.reload_tasks)
            list_header.addWidget(refresh_btn)
            main_lay.addLayout(list_header)

            # --- Task List Scroll Area ---
            self.scroll_area = QScrollArea()
            self.scroll_area.setWidgetResizable(True)
            self.task_container = QWidget()
            self.task_container.setStyleSheet("background: transparent;")
            self.task_layout = QVBoxLayout(self.task_container)
            self.task_layout.setContentsMargins(8, 8, 8, 8)
            self.task_layout.setSpacing(8)
            self.task_layout.addStretch()
            self.scroll_area.setWidget(self.task_container)
            main_lay.addWidget(self.scroll_area, stretch=1)

            # --- Footer ---
            footer = QHBoxLayout()
            hint_lbl = QLabel(f"Offline recipient: {DEFAULT_EMAIL_RECIPIENT}  •  Saved in memory/todo_schedule.json")
            hint_lbl.setStyleSheet("font-size: 10px; color: #4e6e84;")
            footer.addWidget(hint_lbl)
            footer.addStretch()

            close_btn = QPushButton("Close")
            close_btn.setStyleSheet("""
                QPushButton {
                    background-color: #14243b;
                    color: #a4c4d9;
                    border: 1px solid #1e3a5f;
                    padding: 6px 14px;
                }
                QPushButton:hover {
                    background-color: #1e3a5f;
                    color: #ffffff;
                }
            """)
            close_btn.clicked.connect(self.close)
            footer.addWidget(close_btn)
            main_lay.addLayout(footer)

            # Initial load
            self.reload_tasks()

            # Set focus to text box
            QTimer.singleShot(100, self.task_input.setFocus)

        def _add_task_action(self):
            raw_text = self.task_input.text().strip()
            if not raw_text:
                self.feedback_lbl.setText("Please enter a task name.")
                self.feedback_lbl.setStyleSheet("font-size: 11px; color: #ff5555;")
                return

            manual_time = self.time_input.text().strip()
            parsed = parse_task_string(raw_text)
            title = parsed.get("title") or raw_text
            due_date = parsed.get("due_date")
            due_time = manual_time or parsed.get("due_time")
            desc = parsed.get("description") or f"Task: {title}"

            task = add_task(
                title=title,
                description=desc,
                due_date=due_date,
                due_time=due_time,
                until_done=self.until_done_chk.isChecked(),
            )

            self.task_input.clear()
            self.time_input.clear()
            self.feedback_lbl.setText(
                f"[OK] Added '{task['title']}' for {task['due_date']} at {task['due_time']}."
            )
            self.feedback_lbl.setStyleSheet("font-size: 11px; color: #00ff88;")
            self.reload_tasks()

        def reload_tasks(self):
            # Clear existing items
            while self.task_layout.count() > 1:
                item = self.task_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            tasks = list_tasks()
            if not tasks:
                empty_lbl = QLabel("No tasks scheduled yet. Enter a task above to schedule.")
                empty_lbl.setStyleSheet("color: #7f9eb2; font-style: italic; padding: 20px;")
                empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.task_layout.insertWidget(0, empty_lbl)
                return

            for t in tasks:
                card = self._create_task_card(t)
                self.task_layout.insertWidget(self.task_layout.count() - 1, card)

        def _create_task_card(self, t: dict) -> QWidget:
            card = QFrame()
            is_done = t.get("status") == "completed"
            border_color = "#00ff88" if is_done else "#00d2ff"
            bg_color = "#07171f" if is_done else "#091424"

            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_color};
                    border: 1px solid {border_color}44;
                    border-left: 3px solid {border_color};
                    border-radius: 6px;
                    padding: 8px 12px;
                }}
            """)

            c_lay = QHBoxLayout(card)
            c_lay.setContentsMargins(6, 6, 6, 6)
            c_lay.setSpacing(10)

            # Left: Details
            info_v = QVBoxLayout()
            info_v.setSpacing(3)

            title_row = QHBoxLayout()
            title_text = t.get("title", "Untitled")
            if is_done:
                title_text = f"✓ {title_text}"
            title_lbl = QLabel(title_text)
            title_style = "font-size: 13px; font-weight: bold; color: #ffffff;"
            if is_done:
                title_style = "font-size: 13px; color: #7f9eb2; text-decoration: line-through;"
            title_lbl.setStyleSheet(title_style)
            title_row.addWidget(title_lbl)

            # Mode pill
            mode_lbl = QLabel("Voice & Email" if t.get("until_done") else "One-Time")
            mode_lbl.setStyleSheet("""
                font-size: 9px;
                color: #00d2ff;
                padding: 1px 6px;
                border: 1px solid #00d2ff44;
                border-radius: 8px;
            """)
            title_row.addWidget(mode_lbl)
            title_row.addStretch()
            info_v.addLayout(title_row)

            # Sub details
            due_info = f"Due: {t.get('due_date', '')} at {t.get('due_time', '')}"
            if t.get("retry_count", 0) > 0:
                due_info += f"  (Retries: {t['retry_count']})"
            sub_lbl = QLabel(due_info)
            sub_lbl.setStyleSheet("font-size: 11px; color: #7f9eb2;")
            info_v.addWidget(sub_lbl)

            if t.get("description") and t.get("description") != f"Task: {t.get('title')}":
                desc_lbl = QLabel(t["description"])
                desc_lbl.setStyleSheet("font-size: 10px; color: #5a7d94;")
                desc_lbl.setWordWrap(True)
                info_v.addWidget(desc_lbl)

            c_lay.addLayout(info_v, stretch=1)

            # Right: Action Buttons
            btn_v = QHBoxLayout()
            btn_v.setSpacing(6)

            if not is_done:
                done_btn = QPushButton("✓ Done")
                done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                done_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #00aa66;
                        color: #ffffff;
                        border: 1px solid #00ff88;
                        border-radius: 4px;
                        padding: 5px 10px;
                        font-size: 11px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #00cc77;
                    }
                """)
                done_btn.clicked.connect(lambda _, tid=t["task_id"]: self._mark_done(tid))
                btn_v.addWidget(done_btn)

                # Test Run button
                run_btn = QPushButton("▶ Run")
                run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                run_btn.setToolTip("Trigger notification immediately")
                run_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1e3a5f;
                        color: #00d2ff;
                        border: 1px solid #00d2ff;
                        border-radius: 4px;
                        padding: 5px 8px;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: #2b5285;
                    }
                """)
                run_btn.clicked.connect(lambda _, tid=t["task_id"]: self._run_now(tid))
                btn_v.addWidget(run_btn)

            del_btn = QPushButton("✕")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setToolTip("Delete Task")
            del_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a151b;
                    color: #ff6677;
                    border: 1px solid #ff4455;
                    border-radius: 4px;
                    padding: 5px 8px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #551d26;
                }
            """)
            del_btn.clicked.connect(lambda _, tid=t["task_id"]: self._delete_task(tid))
            btn_v.addWidget(del_btn)

            c_lay.addLayout(btn_v)
            return card

        def _mark_done(self, task_id: str):
            complete_task(task_id)
            self.reload_tasks()

        def _delete_task(self, task_id: str):
            delete_task(task_id)
            self.reload_tasks()

        def _run_now(self, task_id: str):
            def _runner():
                res = execute_or_notify_task(task_id, force=True)
                msg = res.get("message", "Task triggered")
                self.feedback_lbl.setText(f"[Notification] {msg}")
            threading.Thread(target=_runner, daemon=True).start()

    app = parent_app or QApplication.instance()
    is_standalone = app is None
    if is_standalone:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")

    dialog = JarvisTodoDialog()
    if is_standalone:
        dialog.show()
        app.exec()
    else:
        dialog.exec()
    return dialog


def _launch_tkinter_dialog():
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("J.A.R.V.I.S. — To-Do & Task Scheduler")
    root.geometry("680x520")
    root.configure(bg="#060b13")

    header_frame = tk.Frame(root, bg="#060b13")
    header_frame.pack(fill=tk.X, padx=16, pady=12)

    title_lbl = tk.Label(
        header_frame,
        text="J.A.R.V.I.S  ·  TO-DO MANAGER",
        font=("Segoe UI", 14, "bold"),
        fg="#00d2ff",
        bg="#060b13",
    )
    title_lbl.pack(anchor="w")

    online, _ = is_user_online()
    sub_lbl = tk.Label(
        header_frame,
        text=f"Status: {'ONLINE (Voice alert)' if online else 'OFFLINE (Email to ' + DEFAULT_EMAIL_RECIPIENT + ')'}",
        font=("Segoe UI", 9),
        fg="#00ff88" if online else "#ffaa00",
        bg="#060b13",
    )
    sub_lbl.pack(anchor="w")

    # Input Frame
    in_frame = tk.LabelFrame(root, text=" Enter Task or Schedule ", fg="#00d2ff", bg="#091322", padx=10, pady=10)
    in_frame.pack(fill=tk.X, padx=16, pady=6)

    task_var = tk.StringVar()
    entry = tk.Entry(in_frame, textvariable=task_var, font=("Segoe UI", 11), bg="#0b1524", fg="#ffffff", insertbackground="#00d2ff")
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), pady=4)

    def do_add():
        text = task_var.get().strip()
        if not text:
            return
        parsed = parse_task_string(text)
        add_task(
            title=parsed.get("title") or text,
            description=parsed.get("description") or f"Task: {text}",
            due_date=parsed.get("due_date"),
            due_time=parsed.get("due_time"),
            until_done=True,
        )
        task_var.set("")
        refresh_list()

    add_btn = tk.Button(in_frame, text="+ ADD TASK", bg="#00d2ff", fg="#060b13", font=("Segoe UI", 9, "bold"), command=do_add)
    add_btn.pack(side=tk.RIGHT)
    entry.bind("<Return>", lambda e: do_add())

    # Task List
    list_frame = tk.Frame(root, bg="#060b13")
    list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

    listbox = tk.Listbox(list_frame, font=("Segoe UI", 10), bg="#0b1524", fg="#ffffff", selectbackground="#1e3a5f")
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    scrollbar = tk.Scrollbar(list_frame, command=listbox.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    listbox.config(yscrollcommand=scrollbar.set)

    loaded_tasks = []

    def refresh_list():
        nonlocal loaded_tasks
        listbox.delete(0, tk.END)
        loaded_tasks = list_tasks()
        for t in loaded_tasks:
            status = "✓ DONE" if t.get("status") == "completed" else "○ PENDING"
            time_str = f"{t.get('due_date')} {t.get('due_time')}"
            listbox.insert(tk.END, f"[{status}]  {t.get('title')}  ({time_str})")

    btn_frame = tk.Frame(root, bg="#060b13")
    btn_frame.pack(fill=tk.X, padx=16, pady=8)

    def do_done():
        sel = listbox.curselection()
        if sel and sel[0] < len(loaded_tasks):
            t = loaded_tasks[sel[0]]
            complete_task(t["task_id"])
            refresh_list()

    def do_delete():
        sel = listbox.curselection()
        if sel and sel[0] < len(loaded_tasks):
            t = loaded_tasks[sel[0]]
            delete_task(t["task_id"])
            refresh_list()

    tk.Button(btn_frame, text="✓ Mark Done", bg="#00aa66", fg="#ffffff", command=do_done).pack(side=tk.LEFT, padx=4)
    tk.Button(btn_frame, text="✕ Delete", bg="#aa3344", fg="#ffffff", command=do_delete).pack(side=tk.LEFT, padx=4)
    tk.Button(btn_frame, text="↺ Refresh", bg="#1e3a5f", fg="#d8ecf8", command=refresh_list).pack(side=tk.LEFT, padx=4)
    tk.Button(btn_frame, text="Close", bg="#14243b", fg="#d8ecf8", command=root.destroy).pack(side=tk.RIGHT, padx=4)

    refresh_list()
    entry.focus_set()
    root.mainloop()


def open_todo_window(parent_app=None):
    """Opens the To-Do input window using PyQt6 if available, falling back to Tkinter."""
    try:
        from PyQt6.QtWidgets import QApplication
        return _launch_pyqt_dialog(parent_app=parent_app)
    except Exception as exc:
        print(f"[TodoDialog] PyQt6 window launch failed: {exc}, using Tkinter fallback...")
        return _launch_tkinter_dialog()


if __name__ == "__main__":
    open_todo_window()
