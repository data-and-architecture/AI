import unittest

from agent.audit import audit_node, audit_start_node


class AuditTests(unittest.TestCase):

    def _state(self):
        return {
            "request_id": "request-123",
            "correlation_id": "correlation-456",
            "security_context": {
                "user": {
                    "user_id": "user-1",
                    "username": "ravi",
                    "roles": ["DATA_ANALYST"],
                }
            },
            "query_plan": {
                "metric": "employee_count",
                "dimensions": ["department"],
                "datasets": ["employees", "departments"],
            },
            "sql_compilation": {
                "metric_id": "employee_count",
                "dimensions": [{"dimension_id": "department"}],
            },
            "policy_decision": {
                "allowed": True,
                "row_filters": [{"dataset_id": "employees"}],
                "masking_rules": [{"column_id": "employees.email"}],
                "limits": {
                    "max_rows": 5000,
                    "max_scan_mb": 512,
                    "max_execution_seconds": 30,
                },
            },
            "sql": "SELECT secret_column FROM employees",
            "sql_parameters": {"filter_1": "sensitive-filter-value"},
            "result": [{"email": "sensitive@example.com", "employee_count": 4}],
            "execution_duration_ms": 12.5,
            "answer": "Verified result: 4",
            "retry_count": 1,
        }

    def test_start_generates_request_and_correlation_ids(self):
        state = audit_start_node({})

        self.assertTrue(state["request_id"])
        self.assertEqual(state["request_id"], state["correlation_id"])
        self.assertTrue(state["audit_started_at"])

    def test_event_records_required_metadata_without_sensitive_payloads(self):
        event = audit_node(self._state())["audit_event"]

        self.assertEqual(event["request_id"], "request-123")
        self.assertEqual(event["correlation_id"], "correlation-456")
        self.assertEqual(event["user"]["roles"], ["DATA_ANALYST"])
        self.assertEqual(event["metadata_version"], "1.0")
        self.assertEqual(event["resolved"]["metric_id"], "employee_count")
        self.assertEqual(event["resolved"]["dimension_ids"], ["department"])
        self.assertEqual(event["resolved"]["dataset_ids"], ["employees", "departments"])
        self.assertTrue(event["policy_decision"]["allowed"])
        self.assertTrue(event["sql_hash"])
        self.assertEqual(event["execution_duration_ms"], 12.5)
        self.assertEqual(event["row_count"], 1)
        self.assertEqual(event["answer_status"], "answered")
        self.assertEqual(event["retry_count"], 1)

        event_text = str(event)
        self.assertNotIn("sensitive@example.com", event_text)
        self.assertNotIn("sensitive-filter-value", event_text)
        self.assertNotIn("SELECT secret_column", event_text)

    def test_denied_request_has_denied_answer_status(self):
        event = audit_node(
            {
                "error": "access denied",
                "error_type": "policy_denied",
                "retry_count": 0,
            }
        )["audit_event"]

        self.assertEqual(event["answer_status"], "denied")
        self.assertEqual(event["error_type"], "policy_denied")
        self.assertIsNone(event["sql_hash"])


if __name__ == "__main__":
    unittest.main()
