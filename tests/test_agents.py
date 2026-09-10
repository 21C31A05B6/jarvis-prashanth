import unittest
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import delete

from agent.agents import AGENTS, GENERAL_AGENT, get_agent, list_agents
from agent.router import is_known_agent, route_message
from api.database import SessionLocal, init_db
from api.models import ChatMessage, User, UserSecret
from api.server import app


class RouterTests(unittest.TestCase):
    """Pure, deterministic — no network calls, no app needed."""

    def test_coding_keywords_route_to_coding(self):
        self.assertEqual(route_message("There's a bug in my python function, can you debug it?"), "coding")

    def test_email_keywords_route_to_email(self):
        self.assertEqual(route_message("Draft a reply to this email from my manager"), "email")

    def test_research_keywords_route_to_research(self):
        self.assertEqual(route_message("Search the web and compare the latest phones"), "research")

    def test_planning_keywords_route_to_planning(self):
        self.assertEqual(route_message("Can you break this down into steps for me?"), "planning")

    def test_computer_keywords_route_to_computer(self):
        self.assertEqual(route_message("Take a screenshot of my screen"), "computer")

    def test_data_keywords_route_to_data(self):
        self.assertEqual(route_message("Analyze this CSV and show me the columns"), "data")

    def test_unmatched_message_routes_to_general(self):
        self.assertEqual(route_message("Good morning!"), "general")

    def test_empty_message_routes_to_general(self):
        self.assertEqual(route_message(""), "general")
        self.assertEqual(route_message("   "), "general")

    def test_is_known_agent(self):
        self.assertTrue(is_known_agent("general"))
        self.assertTrue(is_known_agent("coding"))
        self.assertFalse(is_known_agent("not-a-real-agent"))


class AgentRegistryTests(unittest.TestCase):
    def test_six_specialist_agents_plus_general(self):
        self.assertEqual(len(AGENTS), 6)
        self.assertEqual(
            set(AGENTS),
            {"research", "coding", "email", "computer", "data", "planning"},
        )
        self.assertEqual(len(list_agents()), 7)

    def test_computer_agent_is_desktop_only(self):
        self.assertTrue(AGENTS["computer"].desktop_only)
        for agent_id, agent in AGENTS.items():
            if agent_id != "computer":
                self.assertFalse(agent.desktop_only, agent_id)

    def test_get_agent_falls_back_to_general(self):
        self.assertIs(get_agent(None), GENERAL_AGENT)
        self.assertIs(get_agent("not-a-real-agent"), GENERAL_AGENT)
        self.assertEqual(get_agent("coding").id, "coding")

    def test_only_research_has_a_hosted_tool_today(self):
        # Documents the deliberate scope boundary: every other persona's
        # tools either aren't safe to run headless (browser automation,
        # subprocess execution) or aren't wired up yet.
        hosted = {agent_id: agent.hosted_tool_names for agent_id, agent in AGENTS.items()}
        self.assertEqual(hosted["research"], ("web_search",))
        for agent_id, tools in hosted.items():
            if agent_id != "research":
                self.assertEqual(tools, (), agent_id)


class AgentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.context = cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.email = f"agent-test-{uuid.uuid4().hex}@example.com"
        response = self.client.post("/auth/signup", json={
            "email": self.email,
            "password": "correct-horse-battery-staple",
            "display_name": "Agent Tester",
        })
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}
        # Give the account a (fake) configured key so /chat's precondition
        # check passes; real Gemini calls are mocked per-test below.
        key_response = self.client.post(
            "/me/gemini-key",
            headers=self.headers,
            json={"api_key": "AIza" + "A" * 35, "validate": False},
        )
        assert key_response.status_code == 200, key_response.text

    def tearDown(self):
        with SessionLocal.begin() as db:
            for model in (ChatMessage, UserSecret):
                db.execute(delete(model).where(model.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_agents_endpoint_lists_all_agents_with_availability_flags(self):
        response = self.client.get("/agents", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        by_id = {item["id"]: item for item in response.json()}
        self.assertEqual(set(by_id), {"general", "research", "coding", "email", "computer", "data", "planning"})
        self.assertTrue(by_id["computer"]["desktop_only"])
        self.assertFalse(by_id["computer"]["hosted_capable"])
        self.assertTrue(by_id["research"]["hosted_capable"])
        self.assertTrue(by_id["planning"]["hosted_capable"])

    def test_agents_endpoint_requires_auth(self):
        self.client.cookies.clear()
        response = self.client.get("/agents")
        self.assertEqual(response.status_code, 401)

    def test_chat_rejects_unknown_agent(self):
        response = self.client.post(
            "/chat", headers=self.headers, json={"message": "hi", "agent": "not-a-real-agent"},
        )
        self.assertEqual(response.status_code, 422)

    def test_chat_rejects_desktop_only_agent(self):
        response = self.client.post(
            "/chat", headers=self.headers, json={"message": "take a screenshot", "agent": "computer"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("desktop app", response.json()["detail"])

    def test_chat_with_explicit_coding_agent_uses_that_persona_and_persists_it(self):
        fake_response = MagicMock(text="Here is your function.")
        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = fake_response
            response = self.client.post(
                "/chat", headers=self.headers,
                json={"message": "write me a fibonacci function", "agent": "coding"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["agent"], "coding")
        self.assertEqual(body["response"], "Here is your function.")
        self.assertIsNone(body["plan"])

        # The persona's system instruction should actually have been sent.
        _, kwargs = mock_client_cls.return_value.models.generate_content.call_args
        self.assertIn("Coding agent", kwargs["config"].system_instruction)

        history = self.client.get("/chat/history", headers=self.headers)
        agents_seen = {item["agent"] for item in history.json()["items"]}
        self.assertEqual(agents_seen, {"coding"})

    def test_chat_auto_routes_without_an_explicit_agent(self):
        fake_response = MagicMock(text="Fixed the bug for you.")
        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = fake_response
            response = self.client.post(
                "/chat", headers=self.headers,
                json={"message": "there's a bug in my code, please debug it"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["agent"], "coding")

    def test_chat_with_research_agent_grounds_with_a_real_web_search_call(self):
        fake_response = MagicMock(text="Summarized answer with sources.")
        with patch("agent.tool_runtime.run_web_search") as mock_search, \
             patch("google.genai.Client") as mock_client_cls:
            mock_search.return_value = "SEARCH RESULT: JARVIS is a fictional AI."
            mock_client_cls.return_value.models.generate_content.return_value = fake_response
            response = self.client.post(
                "/chat", headers=self.headers,
                json={"message": "who is JARVIS from Iron Man", "agent": "research"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["agent"], "research")
        mock_search.assert_called_once()

        _, kwargs = mock_client_cls.return_value.models.generate_content.call_args
        self.assertIn("SEARCH RESULT", kwargs["contents"])

    def test_chat_with_planning_agent_returns_a_structured_plan_and_does_not_call_gemini_chat(self):
        fake_plan = {
            "steps": [
                {"step": 1, "tool": "web_search", "description": "Look up flight prices"},
                {"step": 2, "tool": "file_controller", "description": "Save results to a file"},
            ]
        }
        with patch("agent.planner.create_plan", return_value=fake_plan) as mock_plan, \
             patch("google.genai.Client") as mock_client_cls:
            response = self.client.post(
                "/chat", headers=self.headers,
                json={"message": "plan a trip to Tokyo", "agent": "planning"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["agent"], "planning")
        self.assertEqual(len(body["plan"]), 2)
        self.assertEqual(body["plan"][0]["tool"], "web_search")
        mock_plan.assert_called_once()
        # Planning returns the plan directly; it must not also burn a
        # generate_content call against the user's Gemini quota.
        mock_client_cls.return_value.models.generate_content.assert_not_called()

    def test_chat_requires_a_configured_gemini_key(self):
        with SessionLocal.begin() as db:
            db.execute(delete(UserSecret).where(UserSecret.user_id == self.user_id))
        response = self.client.post("/chat", headers=self.headers, json={"message": "hello"})
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
