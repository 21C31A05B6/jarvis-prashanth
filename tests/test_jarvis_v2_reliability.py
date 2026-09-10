"""Comprehensive automated tests for JARVIS V2 reliability improvements.

Validates:
1. ToolResult and ErrorCategory contracts.
2. PermissionManager accessibility and error classification (Categories A-M).
3. File controller and processor verified execution.
4. Open app verification and non-existent app error handling.
5. Code helper command and script returncode verification.
6. Executor tool result verification and artifact forward propagation.
7. Task queue persistence across task lifecycle.
"""

import os
import sys
import tempfile
from pathlib import Path
import unittest

from agent.tool_result import ToolResult, ErrorCategory, coerce_tool_result
from core.permission_manager import (
    classify_error,
    is_path_accessible,
    get_safe_roots,
)


class TestToolResultSystem(unittest.TestCase):
    def test_ok_result(self):
        res = ToolResult.ok("File created", data={"size": 120}, artifacts=["test.txt"])
        self.assertTrue(res.success)
        self.assertEqual(res.status, "completed")
        self.assertEqual(res.artifacts, ["test.txt"])
        self.assertIn("File created", str(res))
        d = res.to_dict()
        self.assertTrue(d["success"])

    def test_fail_result(self):
        res = ToolResult.fail("File not found", ErrorCategory.FILE_NOT_FOUND)
        self.assertFalse(res.success)
        self.assertEqual(res.status, "failed")
        self.assertEqual(res.error_type, "H_file_not_found")
        self.assertIn("H_file_not_found", str(res))

    def test_coerce_tool_result(self):
        # Already ToolResult
        res1 = ToolResult.ok("ok")
        self.assertIs(coerce_tool_result(res1), res1)

        # Success string
        res2 = coerce_tool_result("Everything completed normally.")
        self.assertTrue(res2.success)

        # Error string
        res3 = coerce_tool_result("Error: Access denied to path")
        self.assertFalse(res3.success)
        self.assertEqual(res3.error_type, ErrorCategory.OS_PERMISSION_DENIED.value)

        # None
        res4 = coerce_tool_result(None)
        self.assertFalse(res4.success)


class TestPermissionManager(unittest.TestCase):
    def test_safe_roots_discovery(self):
        roots = get_safe_roots()
        self.assertGreater(len(roots), 0)
        # Home directory should always be safe
        home = Path.home().resolve()
        self.assertTrue(any(home.is_relative_to(r) or r == home for r in roots))

    def test_is_path_accessible(self):
        # Current temp file
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf_path = Path(tf.name)
        try:
            ok, msg = is_path_accessible(tf_path, mode="w")
            self.assertTrue(ok)
        finally:
            tf_path.unlink(missing_ok=True)

    def test_classify_error_categories(self):
        self.assertEqual(classify_error(PermissionError("Access is denied")), ErrorCategory.OS_PERMISSION_DENIED)
        self.assertEqual(classify_error(FileNotFoundError("No such file")), ErrorCategory.FILE_NOT_FOUND)
        self.assertEqual(classify_error(TimeoutError("Operation timed out")), ErrorCategory.TOOL_TIMEOUT)
        self.assertEqual(classify_error(ConnectionError("Network drop")), ErrorCategory.NETWORK_FAILURE)


class TestFileControllerAndProcessor(unittest.TestCase):
    def test_file_controller_crud_verified(self):
        from actions.file_controller import file_controller

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / "jarvis_unit_test.txt"

            # 1. Write file
            write_res = file_controller({
                "action": "create_file",
                "path": str(test_file),
                "content": "Hello JARVIS V2 verified reliability",
            })
            self.assertTrue(write_res.success)
            self.assertTrue(test_file.exists())
            self.assertGreater(test_file.stat().st_size, 0)

            # 2. Read file
            read_res = file_controller({
                "action": "read",
                "path": str(test_file),
            })
            self.assertTrue(read_res.success)
            self.assertIn("Hello JARVIS", read_res.result)

            # 3. List directory
            list_res = file_controller({
                "action": "list",
                "path": tmp_dir,
            })
            self.assertTrue(list_res.success)
            self.assertIn("jarvis_unit_test.txt", list_res.result)

            # 4. Delete file
            del_res = file_controller({
                "action": "delete",
                "path": str(test_file),
            })
            self.assertTrue(del_res.success)
            self.assertFalse(test_file.exists())

    def test_file_processor_directory_analysis(self):
        from actions.file_processor import file_processor

        # Analyze current project root
        repo_root = Path(__file__).resolve().parent.parent
        res = file_processor({
            "action": "analyze_directory",
            "path": str(repo_root),
        })
        self.assertTrue(res.success)
        self.assertIn("Project Architecture", res.result)
        self.assertIn("Python", res.result)


class TestOpenAppVerification(unittest.TestCase):
    def test_open_app_empty(self):
        from actions.open_app import open_app
        res = open_app(parameters={})
        self.assertFalse(res.success)
        self.assertEqual(res.error_type, ErrorCategory.COMMAND_UNDERSTOOD_TOOL_UNAVAILABLE.value)

    def test_open_app_fake_app_fails(self):
        from actions.open_app import open_app
        # An app that definitely does not exist should not return a fake success!
        res = open_app(parameters={"app_name": "TotallyNonExistentApp12345XYZ"})
        self.assertFalse(res.success)
        self.assertEqual(res.error_type, ErrorCategory.APP_NOT_FOUND.value)


class TestCodeHelperVerification(unittest.TestCase):
    def test_code_helper_command_success(self):
        from actions.code_helper import code_helper
        # Running python --version should return returncode 0
        cmd = f'"{sys.executable}" --version'
        res = code_helper(parameters={"action": "run", "description": cmd})
        self.assertTrue(res.success)
        self.assertIn("Python", res.result)

    def test_code_helper_command_failure(self):
        from actions.code_helper import code_helper
        # Running an invalid command or exit code 1
        cmd = f'"{sys.executable}" -c "import sys; sys.exit(1)"'
        res = code_helper(parameters={"action": "run", "description": cmd})
        self.assertFalse(res.success)
        self.assertIn("exit code 1", res.result)


class TestExecutorVerificationAndInjection(unittest.TestCase):
    def test_inject_context_artifacts(self):
        from agent.executor import _inject_context

        step_results = {
            1: "Downloaded file to C:\\Users\\Public\\test_download.pdf (1024 bytes)",
        }
        # In a real environment, if file exists, it injects it
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
            tf_path = tf.name
        try:
            step_results[2] = f"File saved: {tf_path}"
            params = _inject_context({}, "file_processor", step_results)
            self.assertEqual(params.get("path"), tf_path)
        finally:
            Path(tf_path).unlink(missing_ok=True)


class TestTaskQueuePersistence(unittest.TestCase):
    def test_task_queue_record_and_history(self):
        from agent.task_queue import TaskQueue, TaskPriority
        from memory.task_history import get_history, record_task

        # Record directly
        record_task(task_id="test-123", goal="Test persistence", status="completed", result="File saved: C:\\test.txt")
        hist = get_history(limit=5)
        self.assertTrue(any(h.get("task_id") == "test-123" for h in hist))


if __name__ == "__main__":
    unittest.main()
