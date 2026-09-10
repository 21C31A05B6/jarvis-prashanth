import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from actions.tts_engine import DEFAULT_VOICE_ID, PROVIDER_VOICES
from agent.workflow_recorder import WorkflowRecorder
from api.database import SessionLocal, init_db
from api.models import User, UserConfig, Workflow
from api.server import app
from core.tenant import tenant_scope


class WorkflowRecorderUnitTests(unittest.TestCase):
    """Pure unit tests against the recorder object itself — no app, no DB."""

    def test_not_recording_by_default(self):
        recorder = WorkflowRecorder()
        self.assertFalse(recorder.is_recording)

    def test_record_step_is_ignored_when_not_recording(self):
        recorder = WorkflowRecorder()
        recorder.record_step("web_search", {"query": "x"})
        self.assertEqual(recorder._steps, [])

    def test_workflow_controls_own_calls_are_never_recorded(self):
        recorder = WorkflowRecorder()
        recorder.start("test")
        recorder.record_step("workflow_control", {"action": "stop"})
        self.assertEqual(recorder._steps, [])

    def test_stop_without_start_reports_nothing_to_save(self):
        recorder = WorkflowRecorder()
        message = recorder.stop()
        self.assertIn("No workflow", message)

    def test_stop_with_no_captured_steps_does_not_save(self):
        recorder = WorkflowRecorder()
        recorder.start("empty workflow")
        message = recorder.stop()
        self.assertIn("no actions were captured", message)
        self.assertFalse(recorder.is_recording)


class WorkflowStorageTests(unittest.TestCase):
    """Exercises the tenant-aware save/list/find/delete storage functions
    against the real (hosted) database path."""

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.user_id = str(uuid.uuid4())
        with SessionLocal.begin() as db:
            db.add(User(id=self.user_id, email=f"{self.user_id}@example.com", display_name="T", password_hash="x"))

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(Workflow).where(Workflow.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_recorder_save_load_find_delete_round_trip(self):
        from agent.workflow_recorder import delete_workflow_by_name, find_workflow, load_workflows

        recorder = WorkflowRecorder()
        with tenant_scope(self.user_id):
            recorder.start("morning routine")
            recorder.record_step("open_app", {"name": "Slack"})
            recorder.record_step("web_search", {"query": "weather today"})
            message = recorder.stop()
            self.assertIn("2 step", message)

            workflows = load_workflows()
            self.assertEqual(len(workflows), 1)
            self.assertEqual(workflows[0]["name"], "morning routine")
            self.assertEqual(len(workflows[0]["steps"]), 2)

            found = find_workflow("morning routine")
            self.assertIsNotNone(found)
            found_by_id = find_workflow(found["id"])
            self.assertEqual(found_by_id["id"], found["id"])

            self.assertTrue(delete_workflow_by_name("morning routine"))
            self.assertEqual(load_workflows(), [])
            self.assertFalse(delete_workflow_by_name("morning routine"))

    def test_hosted_mode_without_tenant_context_refuses_local_fallback(self):
        import os
        from unittest.mock import patch

        from agent.workflow_recorder import load_workflows

        with patch.dict(os.environ, {"JARVIS_HOSTED": "1"}):
            with self.assertRaises(RuntimeError):
                load_workflows()


class VoiceSettingsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.context = cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.email = f"voice-test-{uuid.uuid4().hex}@example.com"
        response = self.client.post("/auth/signup", json={
            "email": self.email, "password": "correct-horse-battery-staple", "display_name": "Voice Tester",
        })
        body = response.json()
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(UserConfig).where(UserConfig.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_defaults_are_returned_before_any_update(self):
        response = self.client.get("/voice/settings", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["voice_id"], DEFAULT_VOICE_ID)
        self.assertIsNone(body["language"])
        self.assertEqual(len(body["available_voices"]), len(PROVIDER_VOICES["gemini"]))

    def test_updating_voice_and_language_persists(self):
        valid_voice = PROVIDER_VOICES["gemini"][1][1]
        response = self.client.put(
            "/voice/settings", headers=self.headers,
            json={"voice_id": valid_voice, "language": "Hindi"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["voice_id"], valid_voice)
        self.assertEqual(response.json()["language"], "Hindi")

        refetched = self.client.get("/voice/settings", headers=self.headers)
        self.assertEqual(refetched.json()["voice_id"], valid_voice)
        self.assertEqual(refetched.json()["language"], "Hindi")

    def test_rejects_unknown_voice_id(self):
        response = self.client.put("/voice/settings", headers=self.headers, json={"voice_id": "not-a-real-voice"})
        self.assertEqual(response.status_code, 422)

    def test_requires_auth(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/voice/settings").status_code, 401)


class WorkflowApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.context = cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.email = f"workflow-test-{uuid.uuid4().hex}@example.com"
        response = self.client.post("/auth/signup", json={
            "email": self.email, "password": "correct-horse-battery-staple", "display_name": "Workflow Tester",
        })
        body = response.json()
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(Workflow).where(Workflow.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_list_is_empty_then_reflects_created_workflow(self):
        empty = self.client.get("/workflows", headers=self.headers)
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json(), [])

        from api.repositories import create_workflow
        create_workflow(self.user_id, "deploy checklist", [{"tool": "web_search", "parameters": {"query": "status page"}}])

        listed = self.client.get("/workflows", headers=self.headers)
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["name"], "deploy checklist")
        self.assertEqual(listed.json()[0]["steps"][0]["tool"], "web_search")

    def test_delete_workflow(self):
        from api.repositories import create_workflow
        row = create_workflow(self.user_id, "to delete", [])

        response = self.client.delete(f"/workflows/{row.id}", headers=self.headers)
        self.assertEqual(response.status_code, 204)

        missing = self.client.delete(f"/workflows/{row.id}", headers=self.headers)
        self.assertEqual(missing.status_code, 404)

    def test_workflows_are_scoped_per_user(self):
        from api.repositories import create_workflow
        create_workflow(self.user_id, "mine", [])

        other = self.client.post("/auth/signup", json={
            "email": f"other-{uuid.uuid4().hex}@example.com",
            "password": "correct-horse-battery-staple", "display_name": "Other",
        })
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        other_list = self.client.get("/workflows", headers=other_headers)
        self.assertEqual(other_list.json(), [])

        with SessionLocal.begin() as db:
            db.execute(delete(Workflow).where(Workflow.user_id == other.json()["user"]["id"]))
            db.execute(delete(User).where(User.id == other.json()["user"]["id"]))

    def test_requires_auth(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/workflows").status_code, 401)


if __name__ == "__main__":
    unittest.main()
