from threading import Event
import unittest

from fastapi.testclient import TestClient

from agent.api import create_app


class FakeGraph:

    def invoke(self, state):
        return {
            **state,
            "answer": "Verified employee count: 12",
            "result": [{"employee_count": 12}],
            "result_summary": "The query returned 1 rows.",
            "result_verification": {"valid": True, "row_count": 1},
            "sql": "SELECT COUNT(*) AS employee_count FROM employees",
            "error": None,
            "error_type": None,
        }


class ApiTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app(graph_factory=lambda: FakeGraph())
        cls.client = TestClient(cls.app)

    @staticmethod
    def _headers(token="demo-token"):
        return {"Authorization": f"Bearer {token}"}

    def test_chat_returns_governed_shape_and_persists_session(self):
        response = self.client.post(
            "/chat",
            headers=self._headers(),
            json={
                "question": "How many employees are there?",
                "session_id": "session-1",
                "request_id": "request-1",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["request_id"], "request-1")
        self.assertEqual(body["result"], [{"employee_count": 12}])
        self.assertEqual(body["authorized_sql"], None)
        self.assertEqual(body["explanation"]["status"], "verified")

        history = self.client.get("/sessions/session-1", headers=self._headers())
        self.assertEqual(history.status_code, 200)
        self.assertEqual([entry["role"] for entry in history.json()["messages"]], ["user", "assistant"])

    def test_chat_shows_sql_only_to_technical_user(self):
        analyst = self.client.post(
            "/chat",
            headers=self._headers("demo-token"),
            json={"question": "count", "request_id": "request-2"},
        )
        technical = self.client.post(
            "/chat",
            headers=self._headers("technical-token"),
            json={"question": "count", "request_id": "request-3"},
        )

        self.assertIsNone(analyst.json()["authorized_sql"])
        self.assertIn("SELECT COUNT", technical.json()["authorized_sql"])

    def test_requires_authentication_and_enforces_body_limit(self):
        unauthenticated = self.client.post("/chat", json={"question": "count"})
        oversized = self.client.post(
            "/chat",
            headers={**self._headers(), "content-length": "999999"},
            json={"question": "count"},
        )

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(oversized.status_code, 413)

    def test_cancellation_and_admin_access(self):
        cancellation = Event()
        self.app.state.store.register("request-active", cancellation)
        cancelled = self.client.post(
            "/chat/request-active/cancel", headers=self._headers()
        )
        analyst_admin = self.client.get("/admin/metadata", headers=self._headers())
        admin_metadata = self.client.get("/admin/metadata", headers=self._headers("admin-token"))
        admin_audit = self.client.get("/admin/audit", headers=self._headers("admin-token"))

        self.assertEqual(cancelled.status_code, 200)
        self.assertTrue(cancellation.is_set())
        self.assertEqual(analyst_admin.status_code, 403)
        self.assertEqual(admin_metadata.status_code, 200)
        self.assertEqual(admin_metadata.json()["version"], "1.0")
        self.assertEqual(admin_audit.status_code, 200)


if __name__ == "__main__":
    unittest.main()
