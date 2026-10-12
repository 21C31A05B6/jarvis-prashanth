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

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from actions import todo_scheduler


class TodoSchedulerTests(unittest.TestCase):
    def setUp(self):
        # Use an isolated temporary file for storage during tests
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_storage = Path(self.tmp_dir.name) / "test_todo_schedule.json"
        self._orig_storage = todo_scheduler.TODO_STORAGE_PATH
        todo_scheduler.TODO_STORAGE_PATH = self.test_storage

        self._patch_reg = patch("actions.todo_scheduler.register_os_schedule", return_value=True)
        self._patch_del = patch("actions.todo_scheduler.remove_os_schedule", return_value=None)
        self.mock_register_os = self._patch_reg.start()
        self.mock_remove_os = self._patch_del.start()

    def tearDown(self):
        self._patch_reg.stop()
        self._patch_del.stop()
        todo_scheduler.TODO_STORAGE_PATH = self._orig_storage
        self.tmp_dir.cleanup()

    def test_add_and_list_tasks(self):
        task = todo_scheduler.add_task(
            title="Complete project proposal",
            description="Write executive summary and budget",
            due_date="2026-10-15",
            due_time="14:00",
            until_done=True,
            email_recipient="prashanthpogula24@gmail.com",
        )
        self.assertIsNotNone(task)
        self.assertEqual(task["title"], "Complete project proposal")
        self.assertEqual(task["status"], "pending")
        self.assertTrue(task["until_done"])
        self.assertEqual(task["email_recipient"], "prashanthpogula24@gmail.com")

        # Verify persistent storage
        tasks = todo_scheduler.list_tasks("open")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], task["task_id"])

    def test_complete_task(self):
        task = todo_scheduler.add_task(
            title="Read chapter 3",
            description="Algorithm fundamentals",
        )
        completed = todo_scheduler.complete_task(task["task_id"])
        self.assertIsNotNone(completed)
        self.assertEqual(completed["status"], "completed")
        self.assertIsNotNone(completed["completed_at"])

        # Listing open tasks should now be empty
        open_tasks = todo_scheduler.list_tasks("open")
        self.assertEqual(len(open_tasks), 0)

        # Listing completed tasks should have 1
        comp_tasks = todo_scheduler.list_tasks("completed")
        self.assertEqual(len(comp_tasks), 1)

    def test_delete_task(self):
        task = todo_scheduler.add_task(title="Trash me")
        self.assertTrue(todo_scheduler.delete_task(task["task_id"]))
        self.assertEqual(len(todo_scheduler.list_tasks("all")), 0)

    @patch("actions.todo_scheduler.is_user_online", return_value=(True, "User active at workstation"))
    @patch("actions.todo_scheduler.speak_direct")
    def test_execute_online_speaks_directly(self, mock_speak, mock_online):
        task = todo_scheduler.add_task(
            title="Drink water",
            description="Take 500ml water",
            until_done=True,
        )
        result = todo_scheduler.execute_or_notify_task(task["task_id"])
        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "spoken")
        mock_speak.assert_called_once()
        self.assertIn("Drink water", mock_speak.call_args[0][0])

        # Status should be in_progress because until_done is True
        tasks = todo_scheduler.list_tasks("all")
        self.assertEqual(tasks[0]["status"], "in_progress")
        self.assertEqual(tasks[0]["retry_count"], 1)

    @patch("actions.todo_scheduler.is_user_online", return_value=(False, "User idle/away"))
    @patch("actions.todo_scheduler.send_task_email", return_value=(True, "Email dispatched"))
    def test_execute_offline_sends_email(self, mock_email, mock_online):
        task = todo_scheduler.add_task(
            title="Call dentist",
            description="Confirm appointment for 3 PM",
            until_done=True,
            email_recipient="prashanthpogula24@gmail.com",
        )
        result = todo_scheduler.execute_or_notify_task(task["task_id"])
        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "emailed")
        mock_email.assert_called_once()
        self.assertEqual(mock_email.call_args[1]["recipient"], "prashanthpogula24@gmail.com")

    def test_tool_dispatcher_add_and_list(self):
        res = todo_scheduler.todo_scheduler({
            "action": "add",
            "title": "Study physics",
            "due_date": "2026-10-14",
            "due_time": "16:00",
            "until_done": True,
        })
        self.assertIn("Study physics", res)
        self.assertIn("prashanthpogula24@gmail.com", res)

        list_res = todo_scheduler.todo_scheduler({"action": "list"})
        self.assertIn("Study physics", list_res)

    def test_tool_dispatcher_complete_and_delete(self):
        add_res = todo_scheduler.todo_scheduler({
            "action": "add",
            "title": "Clean desk",
        })
        # Extract task_id from add response
        self.assertIn("Clean desk", add_res)

        done_res = todo_scheduler.todo_scheduler({
            "action": "complete",
            "title": "Clean desk",
        })
        self.assertIn("marked completed", done_res)

        del_res = todo_scheduler.todo_scheduler({
            "action": "delete",
            "title": "Clean desk",
        })
        self.assertIn("removed", del_res)

    def test_parse_task_string(self):
        # 1. At specific time
        p1 = todo_scheduler.parse_task_string("Review codebase at 4:30 PM")
        self.assertEqual(p1["title"], "Review codebase")
        self.assertEqual(p1["due_time"], "16:30")

        # 2. Relative time
        p2 = todo_scheduler.parse_task_string("Take a break in 15 minutes")
        self.assertEqual(p2["title"], "Take a break")
        self.assertIsNotNone(p2["due_time"])

        # 3. Tomorrow
        p3 = todo_scheduler.parse_task_string("Call team tomorrow at 10am")
        self.assertEqual(p3["title"], "Call team")
        self.assertEqual(p3["due_time"], "10:00")

        # 4. Prefixes stripped
        p4 = todo_scheduler.parse_task_string("Please remind me to drink water")
        self.assertEqual(p4["title"], "drink water")

    def test_add_task_from_text(self):
        task = todo_scheduler.add_task_from_text("Deploy application at 18:00")
        self.assertEqual(task["title"], "Deploy application")
        self.assertEqual(task["due_time"], "18:00")
        self.assertTrue(task["until_done"])

        # Check storage
        tasks = todo_scheduler.list_tasks("open")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "Deploy application")

    @patch("actions.todo_dialog.open_todo_window")
    def test_tool_dispatcher_gui(self, mock_dialog):
        res = todo_scheduler.todo_scheduler({"action": "gui"})
        self.assertIn("Opening J.A.R.V.I.S To-Do", res)


if __name__ == "__main__":
    unittest.main()

