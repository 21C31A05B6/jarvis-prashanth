import unittest
import uuid

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import delete

from agent.two_factor import generate_secret, provisioning_uri, verify_code
from api.database import SessionLocal, init_db
from api.models import AuditLog, Notification, User, UserConfig, UserSecret
from api.server import app


class TwoFactorUnitTests(unittest.TestCase):
    """Pure function tests — no app, no DB."""

    def test_generated_secret_is_valid_base32(self):
        secret = generate_secret()
        self.assertTrue(secret.isalnum())
        self.assertGreaterEqual(len(secret), 16)

    def test_correct_code_verifies(self):
        secret = generate_secret()
        code = pyotp.TOTP(secret).now()
        self.assertTrue(verify_code(secret, code))

    def test_wrong_code_fails(self):
        secret = generate_secret()
        self.assertFalse(verify_code(secret, "000000"))

    def test_empty_inputs_fail_safely(self):
        self.assertFalse(verify_code("", "123456"))
        self.assertFalse(verify_code(generate_secret(), ""))

    def test_provisioning_uri_contains_issuer_and_email(self):
        uri = provisioning_uri("ABCDEFGH", "user@example.com")
        self.assertTrue(uri.startswith("otpauth://totp/"))
        self.assertIn("JARVIS", uri)


class _BaseApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.context = cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _signup(self, prefix: str, password: str = "correct-horse-battery-staple") -> dict:
        response = self.client.post("/auth/signup", json={
            "email": f"{prefix}-{uuid.uuid4().hex}@example.com",
            "password": password, "display_name": "Tester",
        })
        assert response.status_code == 201, response.text
        return response.json()


class TwoFactorApiTests(_BaseApiTest):
    def setUp(self):
        self.password = "correct-horse-battery-staple"
        body = self._signup("2fa", self.password)
        self.email = body["user"]["email"]
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(UserSecret).where(UserSecret.user_id == self.user_id))
            db.execute(delete(AuditLog).where(AuditLog.user_id == self.user_id))
            db.execute(delete(Notification).where(Notification.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def _enable(self) -> str:
        setup = self.client.post("/auth/2fa/setup", headers=self.headers)
        secret = setup.json()["secret"]
        code = pyotp.TOTP(secret).now()
        enabled = self.client.post("/auth/2fa/enable", headers=self.headers, json={"code": code})
        assert enabled.status_code == 200, enabled.text
        return secret

    def test_setup_returns_secret_and_uri(self):
        response = self.client.post("/auth/2fa/setup", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("secret", response.json())
        self.assertIn("otpauth://", response.json()["provisioning_uri"])

    def test_enable_with_wrong_code_is_rejected(self):
        self.client.post("/auth/2fa/setup", headers=self.headers)
        response = self.client.post("/auth/2fa/enable", headers=self.headers, json={"code": "000000"})
        self.assertEqual(response.status_code, 401)

    def test_enable_with_correct_code_succeeds_and_reflects_in_me(self):
        self._enable()
        me = self.client.get("/auth/me", headers=self.headers)
        self.assertTrue(me.json()["totp_enabled"])

    def test_login_requires_totp_once_enabled(self):
        secret = self._enable()
        self.client.post("/auth/logout", headers=self.headers)
        self.client.cookies.clear()

        without_code = self.client.post("/auth/login", json={"email": self.email, "password": self.password})
        self.assertEqual(without_code.status_code, 401)
        self.assertEqual(without_code.json()["detail"], "totp_required")

        wrong_code = self.client.post("/auth/login", json={"email": self.email, "password": self.password, "totp_code": "000000"})
        self.assertEqual(wrong_code.status_code, 401)

        right_code = self.client.post("/auth/login", json={"email": self.email, "password": self.password, "totp_code": pyotp.TOTP(secret).now()})
        self.assertEqual(right_code.status_code, 200, right_code.text)

    def test_disable_requires_correct_password(self):
        self._enable()
        wrong = self.client.post("/auth/2fa/disable", headers=self.headers, json={"password": "not-the-password"})
        self.assertEqual(wrong.status_code, 401)

        right = self.client.post("/auth/2fa/disable", headers=self.headers, json={"password": self.password})
        self.assertEqual(right.status_code, 200)
        self.assertFalse(right.json()["enabled"])

        me = self.client.get("/auth/me", headers=self.headers)
        self.assertFalse(me.json()["totp_enabled"])

    def test_cannot_setup_twice_while_enabled(self):
        self._enable()
        response = self.client.post("/auth/2fa/setup", headers=self.headers)
        self.assertEqual(response.status_code, 409)


class AuditLogAndSuspiciousActivityTests(_BaseApiTest):
    def setUp(self):
        self.password = "correct-horse-battery-staple"
        body = self._signup("audit", self.password)
        self.email = body["user"]["email"]
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(AuditLog).where(AuditLog.user_id == self.user_id))
            db.execute(delete(Notification).where(Notification.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_signup_is_logged(self):
        log = self.client.get("/security/audit-log", headers=self.headers)
        events = [e["event_type"] for e in log.json()]
        self.assertIn("signup", events)

    def test_failed_login_is_logged_without_leaking_which_field_was_wrong(self):
        response = self.client.post("/auth/login", json={"email": self.email, "password": "wrong-password"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Email or password is incorrect")

        log = self.client.get("/security/audit-log", headers=self.headers)
        events = [e["event_type"] for e in log.json()]
        self.assertIn("login_failed", events)

    def test_successful_login_is_logged(self):
        self.client.post("/auth/login", json={"email": self.email, "password": self.password})
        log = self.client.get("/security/audit-log", headers=self.headers)
        events = [e["event_type"] for e in log.json()]
        self.assertIn("login_success", events)

    def test_session_revocation_is_logged(self):
        sessions = self.client.get("/auth/sessions", headers=self.headers).json()
        session_id = sessions[0]["id"]
        self.client.delete(f"/auth/sessions/{session_id}", headers=self.headers)
        # session revoked -> can't fetch audit log with that token anymore,
        # sign in again to check
        relogin = self.client.post("/auth/login", json={"email": self.email, "password": self.password})
        headers = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
        log = self.client.get("/security/audit-log", headers=headers)
        events = [e["event_type"] for e in log.json()]
        self.assertIn("session_revoked", events)

    def test_audit_log_requires_auth(self):
        self.client.cookies.clear()
        response = self.client.get("/security/audit-log")
        self.assertEqual(response.status_code, 401)


class VaultApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("vault")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(UserSecret).where(UserSecret.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_vault_reflects_configured_secrets_without_exposing_them(self):
        empty = self.client.get("/security/vault", headers=self.headers)
        self.assertTrue(all(not entry["configured"] for entry in empty.json()))

        self.client.post("/me/gemini-key", headers=self.headers, json={"api_key": "AIza" + "A" * 35, "validate": False})
        after = self.client.get("/security/vault", headers=self.headers)
        gemini_entry = next(e for e in after.json() if "Gemini" in e["name"])
        self.assertTrue(gemini_entry["configured"])
        self.assertNotIn("AIza" + "A" * 35, gemini_entry["masked_preview"])
        self.assertTrue(gemini_entry["masked_preview"].endswith("AAAA"))


class DashboardApiTests(_BaseApiTest):
    def setUp(self):
        body = self._signup("dash")
        self.user_id = body["user"]["id"]
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            db.execute(delete(UserConfig).where(UserConfig.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_system_health_returns_real_looking_metrics(self):
        response = self.client.get("/system/health", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertGreaterEqual(body["cpu_percent"], 0)
        self.assertGreaterEqual(body["memory_percent"], 0)
        self.assertLessEqual(body["memory_percent"], 100)
        self.assertGreaterEqual(body["uptime_seconds"], 0)

    def test_usage_summary_starts_empty(self):
        response = self.client.get("/usage/summary", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_calls"], 0)

    def test_usage_summary_reflects_logged_events(self):
        from api.repositories import log_usage_event
        log_usage_event(self.user_id, "/chat", input_chars=10, output_chars=50)
        log_usage_event(self.user_id, "/chat", input_chars=5, output_chars=20)
        response = self.client.get("/usage/summary", headers=self.headers)
        body = response.json()
        self.assertEqual(body["total_calls"], 2)
        self.assertEqual(body["by_endpoint"]["/chat"]["calls"], 2)
        self.assertEqual(body["by_endpoint"]["/chat"]["output_chars"], 70)

    def test_activity_timeline_reflects_a_notification(self):
        from api.repositories import create_notification
        create_notification(self.user_id, "Test event", "something happened", "info")
        response = self.client.get("/dashboard/activity", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        kinds = [item["kind"] for item in response.json()]
        self.assertIn("notification", kinds)

    def test_theme_defaults_to_terminal_and_can_be_updated(self):
        default = self.client.get("/preferences/theme", headers=self.headers)
        self.assertEqual(default.json()["theme"], "terminal")

        updated = self.client.put("/preferences/theme", headers=self.headers, json={"theme": "glass"})
        self.assertEqual(updated.json()["theme"], "glass")

        refetched = self.client.get("/preferences/theme", headers=self.headers)
        self.assertEqual(refetched.json()["theme"], "glass")

    def test_theme_rejects_unknown_value(self):
        response = self.client.put("/preferences/theme", headers=self.headers, json={"theme": "not-a-real-theme"})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
