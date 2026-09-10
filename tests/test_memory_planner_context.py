import json
import unittest
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.database import SessionLocal, init_db
from api.models import ChatMessage, MemoryEntry, TaskRecord, User, UserSecret
from api.repositories import prune_short_term_memory
from api.server import app
from core.tenant import tenant_scope
from memory.memory_manager import load_memory, remember
from memory.semantic_search import semantic_search_memory


class ShortTermMemoryTests(unittest.TestCase):
    """Pure-ish tests against memory_manager's category handling."""

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.user_id = str(uuid.uuid4())
        with SessionLocal.begin() as db:
            db.add(User(id=self.user_id, email=f"{self.user_id}@example.com", display_name="T", password_hash="x"))

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(MemoryEntry).where(MemoryEntry.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_short_term_is_a_recognized_category(self):
        with tenant_scope(self.user_id):
            remember("current_task", "debugging the webhook", category="short_term")
            memory = load_memory()
        self.assertEqual(memory["short_term"]["current_task"]["value"], "debugging the webhook")

    def test_prune_short_term_memory_removes_only_stale_short_term_entries(self):
        from datetime import datetime, timezone

        with tenant_scope(self.user_id):
            remember("stale", "old context", category="short_term")
            remember("keeper", "long term fact", category="identity")
        with SessionLocal.begin() as db:
            db.execute(
                MemoryEntry.__table__.update()
                .where(MemoryEntry.user_id == self.user_id, MemoryEntry.category == "short_term")
                .values(updated_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
            )
        deleted = prune_short_term_memory(ttl_hours=24)
        self.assertGreaterEqual(deleted, 1)
        with tenant_scope(self.user_id):
            memory = load_memory()
        self.assertNotIn("stale", memory["short_term"])
        self.assertIn("keeper", memory["identity"])


class SemanticSearchTests(unittest.TestCase):
    """Pure function test — no network, no app."""

    def test_falls_back_to_keyword_scoring_when_embedding_fails(self):
        memory = {
            "notes": {"fav_language": {"value": "Python is my favorite programming language"}},
            "preferences": {"drink": {"value": "Coffee, black, no sugar"}},
        }
        with patch("google.genai.Client", side_effect=RuntimeError("no network")):
            results = semantic_search_memory(memory, "what programming language do I like", "fake-key", top_k=5)
        self.assertTrue(results)
        self.assertEqual(results[0]["key"], "fav_language")

    def test_empty_memory_returns_no_results(self):
        self.assertEqual(semantic_search_memory({}, "anything", "fake-key"), [])


class MemoryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.context = cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.email = f"memory-test-{uuid.uuid4().hex}@example.com"
        response = self.client.post("/auth/signup", json={
            "email": self.email, "password": "correct-horse-battery-staple", "display_name": "Memory Tester",
        })
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(MemoryEntry).where(MemoryEntry.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_memory_upsert_list_and_delete_round_trip(self):
        create = self.client.put(
            "/memory", headers=self.headers,
            json={"category": "projects", "key": "jarvis", "value": "Building the multi-agent system"},
        )
        self.assertEqual(create.status_code, 200, create.text)
        self.assertEqual(create.json()["value"], "Building the multi-agent system")

        listed = self.client.get("/memory", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        keys = {(item["category"], item["key"]) for item in listed.json()}
        self.assertIn(("projects", "jarvis"), keys)

        filtered = self.client.get("/memory", headers=self.headers, params={"category": "projects"})
        self.assertTrue(all(item["category"] == "projects" for item in filtered.json()))

        deleted = self.client.delete("/memory/projects/jarvis", headers=self.headers)
        self.assertEqual(deleted.status_code, 204)

        gone = self.client.delete("/memory/projects/jarvis", headers=self.headers)
        self.assertEqual(gone.status_code, 404)

    def test_memory_upsert_rejects_unknown_category(self):
        response = self.client.put(
            "/memory", headers=self.headers,
            json={"category": "not-a-real-category", "key": "x", "value": "y"},
        )
        self.assertEqual(response.status_code, 422)

    def test_memory_endpoints_require_auth(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/memory").status_code, 401)

    def test_context_endpoint_reflects_recent_conversation_and_memory(self):
        self.client.put(
            "/memory", headers=self.headers,
            json={"category": "preferences", "key": "tone", "value": "concise"},
        )
        with SessionLocal.begin() as db:
            db.add(ChatMessage(user_id=self.user_id, role="user", content="please debug this python error", agent="coding"))

        context = self.client.get("/context", headers=self.headers)
        self.assertEqual(context.status_code, 200, context.text)
        body = context.json()
        self.assertFalse(body["desktop_features_available"])
        self.assertIn("please debug this python error", body["recent_topics"])
        self.assertEqual(body["active_agent_hint"], "coding")
        self.assertGreaterEqual(body["memory_categories"]["preferences"], 1)

        with SessionLocal.begin() as db:
            db.execute(delete(ChatMessage).where(ChatMessage.user_id == self.user_id))
            db.execute(delete(MemoryEntry).where(MemoryEntry.user_id == self.user_id))


class PlannerAndTaskApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.context = cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.email = f"planner-test-{uuid.uuid4().hex}@example.com"
        response = self.client.post("/auth/signup", json={
            "email": self.email, "password": "correct-horse-battery-staple", "display_name": "Planner Tester",
        })
        body = response.json()
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}
        key_response = self.client.post(
            "/me/gemini-key", headers=self.headers,
            json={"api_key": "AIza" + "A" * 35, "validate": False},
        )
        assert key_response.status_code == 200, key_response.text

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(TaskRecord).where(TaskRecord.user_id == self.user_id))
            db.execute(delete(UserSecret).where(UserSecret.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def _fake_plan(self):
        return {
            "steps": [
                {"step": 1, "tool": "web_search", "description": "Find cheap flights to Tokyo"},
                {"step": 2, "tool": "file_controller", "description": "Save results to a file"},
            ]
        }

    def test_create_plan_persists_a_task_with_steps(self):
        with patch("agent.planner.create_plan", return_value=self._fake_plan()) as mock_plan:
            response = self.client.post("/planner/plan", headers=self.headers, json={"goal": "plan a trip to Tokyo"})
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["status"], "planned")
        self.assertEqual(len(body["steps"]), 2)
        mock_plan.assert_called_once()
        self.task_id = body["task_id"]

        listed = self.client.get("/tasks", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(any(t["task_id"] == body["task_id"] for t in listed.json()))

        fetched = self.client.get(f"/tasks/{body['task_id']}", headers=self.headers)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["goal"], "plan a trip to Tokyo")

    def test_run_task_executes_hosted_safe_steps_and_marks_others_desktop_only(self):
        with patch("agent.planner.create_plan", return_value=self._fake_plan()):
            plan_response = self.client.post("/planner/plan", headers=self.headers, json={"goal": "plan a trip"})
        task_id = plan_response.json()["task_id"]

        with patch("agent.tool_runtime.run_web_search") as mock_search:
            mock_search.return_value = "Flights start at $600 round trip."
            run_response = self.client.post(f"/tasks/{task_id}/run", headers=self.headers)

        self.assertEqual(run_response.status_code, 200, run_response.text)
        body = run_response.json()
        self.assertEqual(body["status"], "partial")  # one completed, one skipped
        steps_by_tool = {step["tool"]: step for step in body["steps"]}
        self.assertEqual(steps_by_tool["web_search"]["status"], "completed")
        self.assertIn("$600", steps_by_tool["web_search"]["output"])
        self.assertEqual(steps_by_tool["file_controller"]["status"], "skipped_desktop_only")
        self.assertIn("desktop app", steps_by_tool["file_controller"]["output"])

    def test_run_task_rejects_unknown_task(self):
        response = self.client.post("/tasks/not-a-real-task/run", headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_run_task_twice_is_rejected_once_completed(self):
        plan = {"steps": [{"step": 1, "tool": "web_search", "description": "search something"}]}
        with patch("agent.planner.create_plan", return_value=plan):
            plan_response = self.client.post("/planner/plan", headers=self.headers, json={"goal": "g"})
        task_id = plan_response.json()["task_id"]

        with patch("agent.tool_runtime.run_web_search", return_value="ok"):
            first = self.client.post(f"/tasks/{task_id}/run", headers=self.headers)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["status"], "completed")
            second = self.client.post(f"/tasks/{task_id}/run", headers=self.headers)
        self.assertEqual(second.status_code, 409)


if __name__ == "__main__":
    unittest.main()
