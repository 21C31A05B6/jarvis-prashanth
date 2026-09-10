import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import delete

from agent.task_runner import flag_steps_needing_approval, run_task_steps, summarize_task_status
from api.database import SessionLocal, init_db
from api.models import (
    CalendarEvent, MeetingNote, Notification, TaskRecord, Todo, User, UserConfig,
)
from api.server import app


class ApprovalGateUnitTests(unittest.TestCase):
    """Pure function tests — no app, no network."""

    def test_write_shaped_steps_are_flagged(self):
        steps = [
            {"step": 1, "tool": "web_search", "description": "look up flight prices"},
            {"step": 2, "tool": "email_control", "description": "send the confirmation email"},
        ]
        flagged = flag_steps_needing_approval(steps)
        self.assertFalse(flagged[0]["requires_approval"])
        self.assertTrue(flagged[0]["approved"])
        self.assertTrue(flagged[1]["requires_approval"])
        self.assertFalse(flagged[1]["approved"])

    def test_summarize_status_awaiting_approval(self):
        results = [{"status": "awaiting_approval"}]
        self.assertEqual(summarize_task_status(results), "awaiting_approval")

    def test_summarize_status_partial_mix(self):
        results = [{"status": "completed"}, {"status": "failed"}]
        self.assertEqual(summarize_task_status(results), "partial")


class TaskRunnerRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_transient_failures_then_succeeds(self):
        calls = {"n": 0}

        async def flaky_search(query):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("rate limited")
            return "ok result"

        steps = [{"step": 1, "tool": "web_search", "description": "x", "approved": True}]
        with patch("agent.tool_runtime.run_web_search", side_effect=flaky_search):
            results = await run_task_steps(steps)
        self.assertEqual(results[0]["status"], "completed")
        self.assertEqual(results[0]["attempts"], 3)

    async def test_gives_up_after_max_attempts(self):
        steps = [{"step": 1, "tool": "web_search", "description": "x", "approved": True}]
        with patch("agent.tool_runtime.run_web_search", side_effect=RuntimeError("down")):
            results = await run_task_steps(steps)
        self.assertEqual(results[0]["status"], "failed")
        self.assertIn("3 attempts", results[0]["output"])

    async def test_awaiting_approval_step_is_never_executed(self):
        with patch("agent.tool_runtime.run_web_search") as mock_search:
            steps = [{"step": 1, "tool": "web_search", "description": "x", "requires_approval": True, "approved": False}]
            results = await run_task_steps(steps)
        mock_search.assert_not_called()
        self.assertEqual(results[0]["status"], "awaiting_approval")


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    async def asyncSetUp(self):
        self.user_id = str(uuid.uuid4())
        with SessionLocal.begin() as db:
            db.add(User(id=self.user_id, email=f"{self.user_id}@example.com", display_name="T", password_hash="x"))

    async def asyncTearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(TaskRecord).where(TaskRecord.user_id == self.user_id))
            db.execute(delete(Notification).where(Notification.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    async def test_due_task_runs_and_creates_notification(self):
        from api.repositories import add_task_record, get_task_record, list_notifications
        from api.scheduler import run_scheduler_tick

        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        add_task_record(self.user_id, {
            "task_id": "sched-1", "goal": "check the weather", "status": "scheduled",
            "steps": json.dumps([{"step": 1, "tool": "web_search", "description": "weather today", "approved": True}]),
            "scheduled_at": past, "recurrence": "none",
        })

        with patch("agent.tool_runtime.run_web_search", return_value="sunny, 22C"):
            ran = await run_scheduler_tick(now=datetime.now(timezone.utc))

        self.assertEqual(ran, 1)
        record = get_task_record(self.user_id, "sched-1")
        self.assertEqual(record["status"], "completed")
        notifications = list_notifications(self.user_id)
        self.assertEqual(len(notifications), 1)
        self.assertIn("check the weather", notifications[0].title)

    async def test_recurring_task_reschedules_itself(self):
        from api.repositories import add_task_record, task_history
        from api.scheduler import run_scheduler_tick

        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        add_task_record(self.user_id, {
            "task_id": "sched-recurring", "goal": "daily search", "status": "scheduled",
            "steps": json.dumps([{"step": 1, "tool": "web_search", "description": "daily news", "approved": True}]),
            "scheduled_at": past, "recurrence": "daily",
        })

        with patch("agent.tool_runtime.run_web_search", return_value="news here"):
            await run_scheduler_tick(now=datetime.now(timezone.utc))

        records = task_history(self.user_id, limit=10)
        statuses = {r["status"] for r in records}
        self.assertIn("completed", statuses)
        self.assertIn("scheduled", statuses)
        next_occurrence = next(r for r in records if r["status"] == "scheduled")
        from api.repositories import as_aware_utc
        self.assertGreater(as_aware_utc(next_occurrence["scheduled_at"]), past + timedelta(hours=23))

    async def test_not_yet_due_task_is_left_alone(self):
        from api.repositories import add_task_record, get_task_record
        from api.scheduler import run_scheduler_tick

        future = datetime.now(timezone.utc) + timedelta(days=1)
        add_task_record(self.user_id, {
            "task_id": "sched-future", "goal": "future task", "status": "scheduled",
            "steps": json.dumps([]), "scheduled_at": future, "recurrence": "none",
        })
        ran = await run_scheduler_tick(now=datetime.now(timezone.utc))
        self.assertEqual(ran, 0)
        record = get_task_record(self.user_id, "sched-future")
        self.assertEqual(record["status"], "scheduled")


class _BaseApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.context = cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _signup(self, prefix: str) -> dict:
        response = self.client.post("/auth/signup", json={
            "email": f"{prefix}-{uuid.uuid4().hex}@example.com",
            "password": "correct-horse-battery-staple", "display_name": "Tester",
        })
        assert response.status_code == 201, response.text
        return response.json()

    def _with_gemini_key(self, headers: dict) -> None:
        response = self.client.post(
            "/me/gemini-key", headers=headers,
            json={"api_key": "AIza" + "A" * 35, "validate": False},
        )
        assert response.status_code == 200, response.text


class TodoApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("todo")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(Todo).where(Todo.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_create_list_toggle_delete(self):
        create = self.client.post("/todos", headers=self.headers, json={"text": "write report"})
        self.assertEqual(create.status_code, 201, create.text)
        todo_id = create.json()["id"]

        listed = self.client.get("/todos", headers=self.headers)
        self.assertEqual(len(listed.json()), 1)

        toggled = self.client.put(f"/todos/{todo_id}/done", headers=self.headers, params={"done": True})
        self.assertTrue(toggled.json()["done"])

        only_open = self.client.get("/todos", headers=self.headers, params={"done": False})
        self.assertEqual(only_open.json(), [])

        deleted = self.client.delete(f"/todos/{todo_id}", headers=self.headers)
        self.assertEqual(deleted.status_code, 204)


class CalendarApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("cal")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(CalendarEvent).where(CalendarEvent.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_create_list_filter_delete(self):
        start = datetime.now(timezone.utc)
        create = self.client.post(
            "/calendar/events", headers=self.headers,
            json={"title": "1:1 with manager", "start_at": start.isoformat()},
        )
        self.assertEqual(create.status_code, 201, create.text)
        event_id = create.json()["id"]

        listed = self.client.get("/calendar/events", headers=self.headers)
        self.assertEqual(len(listed.json()), 1)

        out_of_range = self.client.get(
            "/calendar/events", headers=self.headers,
            params={"start": (start + timedelta(days=5)).isoformat()},
        )
        self.assertEqual(out_of_range.json(), [])

        deleted = self.client.delete(f"/calendar/events/{event_id}", headers=self.headers)
        self.assertEqual(deleted.status_code, 204)


class NotificationApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("notif")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(Notification).where(Notification.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_list_read_delete(self):
        from api.repositories import create_notification

        row = create_notification(self.user_id, "Task done", "your task finished", "task")

        listed = self.client.get("/notifications", headers=self.headers)
        self.assertEqual(len(listed.json()), 1)

        unread = self.client.get("/notifications", headers=self.headers, params={"unread_only": True})
        self.assertEqual(len(unread.json()), 1)

        read = self.client.post(f"/notifications/{row.id}/read", headers=self.headers)
        self.assertEqual(read.status_code, 204)

        unread_after = self.client.get("/notifications", headers=self.headers, params={"unread_only": True})
        self.assertEqual(unread_after.json(), [])

        deleted = self.client.delete(f"/notifications/{row.id}", headers=self.headers)
        self.assertEqual(deleted.status_code, 204)


class AgentPermissionsApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("perm")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}
        self._with_gemini_key(self.headers)

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(UserConfig).where(UserConfig.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_default_has_nothing_disabled(self):
        response = self.client.get("/agents/permissions", headers=self.headers)
        self.assertEqual(response.json()["disabled_agents"], [])

    def test_disabling_general_is_rejected(self):
        response = self.client.put("/agents/permissions", headers=self.headers, json={"disabled_agents": ["general"]})
        self.assertEqual(response.status_code, 422)

    def test_disabled_agent_blocks_chat(self):
        self.client.put("/agents/permissions", headers=self.headers, json={"disabled_agents": ["coding"]})
        response = self.client.post("/chat", headers=self.headers, json={"message": "hi", "agent": "coding"})
        self.assertEqual(response.status_code, 403)


class ResearchApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("research")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}
        self._with_gemini_key(self.headers)

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(User).where(User.id == self.user_id))

    def test_compare_runs_hosted_safe_search(self):
        with patch("actions.web_search.web_search", return_value="A vs B: A wins on price") as mock_search:
            response = self.client.post(
                "/research/compare", headers=self.headers,
                json={"items": ["Product A", "Product B"]},
            )
        self.assertEqual(response.status_code, 200, response.text)
        mock_search.assert_called_once()

    def test_report_queries_multiple_angles_and_synthesizes(self):
        with patch("agent.tool_runtime.run_web_search", return_value="some findings") as mock_search, \
             patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = MagicMock(text="Synthesized report")
            response = self.client.post(
                "/research/report", headers=self.headers,
                json={"topic": "electric cars", "angles": ["EV battery tech", "EV market share"]},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["report"], "Synthesized report")
        self.assertEqual(mock_search.call_count, 2)
        self.assertEqual(set(body["sources_queried"]), {"EV battery tech", "EV market share"})

    def test_summarize_text_returns_structured_output(self):
        fake_json = '{"summary": "A short summary.", "key_points": ["point one", "point two"]}'
        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = MagicMock(text=fake_json)
            response = self.client.post(
                "/research/summarize-text", headers=self.headers,
                json={"text": "Some long article text..."},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["key_points"], ["point one", "point two"])


class MeetingAssistantApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("meeting")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}
        self._with_gemini_key(self.headers)

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(MeetingNote).where(MeetingNote.user_id == self.user_id))
            db.execute(delete(Todo).where(Todo.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_summarize_meeting_and_create_todos(self):
        fake_json = '{"summary": "We discussed Q3 goals.", "action_items": ["Follow up with design", "Send the deck"]}'
        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = MagicMock(text=fake_json)
            response = self.client.post(
                "/meetings/summarize", headers=self.headers,
                json={"title": "Q3 planning", "transcript": "...", "create_todos": True},
            )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(len(response.json()["action_items"]), 2)

        todos = self.client.get("/todos", headers=self.headers)
        self.assertEqual(len(todos.json()), 2)

        meetings = self.client.get("/meetings", headers=self.headers)
        self.assertEqual(len(meetings.json()), 1)


class DocumentGeneratorApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("doc")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(User).where(User.id == self.user_id))

    def test_generates_a_downloadable_docx(self):
        response = self.client.post(
            "/documents/generate", headers=self.headers,
            json={"title": "My Report", "content": "Intro paragraph.\n\n- bullet one\n- bullet two"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("wordprocessingml", response.headers["content-type"])
        self.assertGreater(len(response.content), 1000)
        self.assertIn("My Report", response.headers["content-disposition"])


class DailyBriefingApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("brief")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(Todo).where(Todo.user_id == self.user_id))
            db.execute(delete(CalendarEvent).where(CalendarEvent.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_briefing_reflects_todays_items(self):
        now = datetime.now(timezone.utc)
        self.client.post("/todos", headers=self.headers, json={"text": "due today", "due_at": now.isoformat()})
        self.client.post(
            "/calendar/events", headers=self.headers,
            json={"title": "today's meeting", "start_at": now.isoformat()},
        )
        response = self.client.get("/daily-briefing", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["todos_due_today"]), 1)
        self.assertEqual(len(body["events_today"]), 1)
        self.assertIn("event", body["greeting"])


if __name__ == "__main__":
    unittest.main()
