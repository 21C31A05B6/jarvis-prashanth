import unittest
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import delete

from agent.data_analyst import _is_read_only, analyze_csv
from api.database import SessionLocal, init_db
from api.models import User, UserSecret
from api.server import app


class DataAnalystUnitTests(unittest.TestCase):
    """Pure function tests — no app, no network."""

    def setUp(self):
        self.csv = "name,age,city\nAlice,30,NYC\nBob,25,LA\nCarol,35,NYC\n"

    def test_analyze_reports_row_and_column_counts(self):
        result = analyze_csv(self.csv)
        self.assertEqual(result["row_count"], 3)
        self.assertEqual(result["column_count"], 3)

    def test_numeric_column_gets_descriptive_stats(self):
        result = analyze_csv(self.csv)
        age_col = next(c for c in result["columns"] if c["name"] == "age")
        self.assertEqual(age_col["min"], 25.0)
        self.assertEqual(age_col["max"], 35.0)

    def test_categorical_column_gets_top_values(self):
        result = analyze_csv(self.csv)
        city_col = next(c for c in result["columns"] if c["name"] == "city")
        self.assertIsNotNone(city_col["top_values"])
        top = {v["value"]: v["count"] for v in city_col["top_values"]}
        self.assertEqual(top["NYC"], 2)

    def test_chart_spec_is_generated_from_numeric_column(self):
        result = analyze_csv(self.csv)
        self.assertIsNotNone(result["chart"])
        self.assertEqual(result["chart"]["chart_type"], "bar")

    def test_read_only_sql_gate(self):
        self.assertTrue(_is_read_only("SELECT * FROM data"))
        self.assertTrue(_is_read_only("select name, age from data where age > 20"))
        self.assertFalse(_is_read_only("DROP TABLE data"))
        self.assertFalse(_is_read_only("SELECT * FROM data; DROP TABLE data"))
        self.assertFalse(_is_read_only("INSERT INTO data VALUES (1)"))
        self.assertFalse(_is_read_only("UPDATE data SET age = 1"))


class DocumentGeneratorPdfUnitTests(unittest.TestCase):
    def test_pdf_has_correct_single_page_text_and_no_duplicate_content(self):
        from agent.document_generator import generate_pdf
        import pymupdf

        pdf_bytes = generate_pdf("Test Title", "Body paragraph one.\n\nBody paragraph two.")
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(doc.page_count, 1)
        text = doc[0].get_text()
        self.assertEqual(text.count("Test Title"), 1)
        self.assertIn("Body paragraph one.", text)

    def test_pdf_paginates_long_content_without_losing_or_duplicating_text(self):
        from agent.document_generator import generate_pdf
        import pymupdf

        long_content = "\n\n".join(f"Paragraph {i}: " + ("word " * 200) for i in range(20))
        pdf_bytes = generate_pdf("Long Report", long_content)
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        self.assertGreater(doc.page_count, 1)
        full_text = "".join(page.get_text() for page in doc)
        self.assertEqual(full_text.count("Paragraph 0:"), 1)
        self.assertEqual(full_text.count("Paragraph 19:"), 1)

    def test_docx_still_generates_correctly(self):
        from agent.document_generator import generate_docx
        docx_bytes = generate_docx("Doc", "Hello\n\n- one\n- two")
        self.assertGreater(len(docx_bytes), 1000)


class GitHubClientUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_repos_maps_fields(self):
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = [{
            "full_name": "octocat/hello-world", "description": "desc", "private": False,
            "default_branch": "main", "open_issues_count": 3, "html_url": "https://github.com/x",
        }]
        with patch("agent.github_client.requests.get", return_value=fake_response):
            from agent.github_client import list_repos
            repos = await list_repos("fake-token")
        self.assertEqual(repos[0]["full_name"], "octocat/hello-world")
        self.assertEqual(repos[0]["open_issues"], 3)

    async def test_invalid_token_raises_permission_error(self):
        fake_response = MagicMock()
        fake_response.status_code = 401
        with patch("agent.github_client.requests.get", return_value=fake_response):
            from agent.github_client import list_repos
            with self.assertRaises(PermissionError):
                await list_repos("bad-token")

    async def test_not_found_raises_lookup_error(self):
        fake_response = MagicMock()
        fake_response.status_code = 404
        with patch("agent.github_client.requests.get", return_value=fake_response):
            from agent.github_client import list_issues
            with self.assertRaises(LookupError):
                await list_issues("token", "nope", "nope")


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


class DevAssistantApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("dev")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}
        self._with_gemini_key(self.headers)

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(UserSecret).where(UserSecret.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_debug_returns_explanation_and_fix(self):
        fake_json = '{"explanation": "off by one error", "fix": "for i in range(len(x)):"}'
        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = MagicMock(text=fake_json)
            response = self.client.post(
                "/dev/debug", headers=self.headers,
                json={"code": "for i in range(len(x)+1): print(x[i])", "error": "IndexError", "language": "python"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("off by one", response.json()["explanation"])

    def test_generate_tests_returns_test_code(self):
        fake_json = '{"tests": "def test_add(): assert add(1,2)==3", "framework": "pytest"}'
        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = MagicMock(text=fake_json)
            response = self.client.post(
                "/dev/generate-tests", headers=self.headers,
                json={"code": "def add(a, b): return a + b", "language": "python"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["framework"], "pytest")

    def test_review_returns_structured_feedback(self):
        fake_json = '{"summary": "solid", "strengths": ["clear"], "concerns": ["no tests"], "suggestions": ["add tests"]}'
        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = MagicMock(text=fake_json)
            response = self.client.post("/dev/review", headers=self.headers, json={"description": "A Flask app with 3 routes."})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["concerns"], ["no tests"])

    def test_suggest_command_returns_structured_result(self):
        fake_json = '{"command": "find . -name \\"*.py\\" | xargs wc -l", "explanation": "counts lines", "caution": ""}'
        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = MagicMock(text=fake_json)
            response = self.client.post("/dev/suggest-command", headers=self.headers, json={"task": "count lines of python code", "shell": "bash"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("wc -l", response.json()["command"])

    def test_requires_gemini_key(self):
        with SessionLocal.begin() as db:
            db.execute(delete(UserSecret).where(UserSecret.user_id == self.user_id))
        response = self.client.post("/dev/debug", headers=self.headers, json={"code": "x", "error": "y"})
        self.assertEqual(response.status_code, 409)


class GitHubApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("gh")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(UserSecret).where(UserSecret.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_requires_token_before_listing_repos(self):
        response = self.client.get("/dev/github/repos", headers=self.headers)
        self.assertEqual(response.status_code, 409)

    def test_saves_token_and_lists_repos(self):
        saved = self.client.post("/me/github-token", headers=self.headers, json={"token": "ghp_faketoken1234567890"})
        self.assertEqual(saved.status_code, 200, saved.text)

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = [{
            "full_name": "me/myrepo", "description": None, "private": True,
            "default_branch": "main", "open_issues_count": 0, "html_url": "https://github.com/me/myrepo",
        }]
        with patch("agent.github_client.requests.get", return_value=fake_response):
            response = self.client.get("/dev/github/repos", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()[0]["full_name"], "me/myrepo")

    def test_create_issue(self):
        self.client.post("/me/github-token", headers=self.headers, json={"token": "ghp_faketoken1234567890"})
        fake_response = MagicMock()
        fake_response.status_code = 201
        fake_response.json.return_value = {"number": 42, "title": "Bug found", "html_url": "https://github.com/me/repo/issues/42"}
        with patch("agent.github_client.requests.post", return_value=fake_response):
            response = self.client.post(
                "/dev/github/repos/me/repo/issues", headers=self.headers,
                json={"title": "Bug found", "body": "details"},
            )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["number"], 42)

    def test_delete_token(self):
        self.client.post("/me/github-token", headers=self.headers, json={"token": "ghp_faketoken1234567890"})
        deleted = self.client.delete("/me/github-token", headers=self.headers)
        self.assertEqual(deleted.status_code, 204)
        response = self.client.get("/dev/github/repos", headers=self.headers)
        self.assertEqual(response.status_code, 409)


class DataApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("data")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}
        self._with_gemini_key(self.headers)
        self.csv = "product,price,units_sold\nWidget,9.99,100\nGadget,19.99,50\nGizmo,29.99,25\n"

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(UserSecret).where(UserSecret.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_analyze_csv_endpoint(self):
        response = self.client.post("/data/analyze", headers=self.headers, json={"csv_text": self.csv})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["row_count"], 3)
        self.assertIsNotNone(body["chart"])

    def test_analyze_rejects_malformed_csv(self):
        response = self.client.post("/data/analyze", headers=self.headers, json={"csv_text": ""})
        self.assertIn(response.status_code, (422,))

    def test_query_data_executes_generated_sql_safely(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = MagicMock(
                text="SELECT product, price FROM data WHERE price > 15"
            )
            response = self.client.post(
                "/data/query", headers=self.headers,
                json={"csv_text": self.csv, "question": "which products cost more than 15?"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["columns"], ["product", "price"])
        self.assertEqual(len(body["rows"]), 2)

    def test_query_data_rejects_a_generated_write_query(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = MagicMock(
                text="DROP TABLE data"
            )
            response = self.client.post(
                "/data/query", headers=self.headers,
                json={"csv_text": self.csv, "question": "delete everything"},
            )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
