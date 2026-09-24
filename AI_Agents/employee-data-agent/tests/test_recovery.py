import unittest
from unittest.mock import patch

from agent.database import execute_sql
from agent.recovery import recovery_node
from agent.router import route_after_recovery


class RecoveryTests(unittest.TestCase):

    def test_policy_and_ambiguity_fail_closed_without_retry(self):
        denied = recovery_node({"error": "denied", "error_type": "policy_denied"})
        unavailable = recovery_node(
            {"error": "unavailable", "error_type": "policy_unavailable"}
        )
        ambiguous = recovery_node(
            {"error": "clarify", "error_type": "ambiguous_term"}
        )

        self.assertEqual(route_after_recovery(denied), "answer")
        self.assertEqual(route_after_recovery(unavailable), "answer")
        self.assertEqual(route_after_recovery(ambiguous), "answer")

    def test_unknown_metric_retries_discovery_once_then_clarifies(self):
        first = recovery_node(
            {"error": "missing", "error_type": "unknown_metric", "retry_count": 0}
        )
        second = recovery_node(
            {"error": "missing", "error_type": "unknown_metric", "retry_count": 1}
        )

        self.assertEqual(route_after_recovery(first), "retry_metadata")
        self.assertEqual(first["retry_count"], 1)
        self.assertIsNone(first["error"])
        self.assertEqual(route_after_recovery(second), "answer")
        self.assertEqual(second["error_type"], "clarification_required")
        self.assertIn("Which approved metric", second["query_understanding"]["clarification_question"])

    def test_invalid_dimension_and_sql_retry_from_metadata_with_bound(self):
        dimension = recovery_node(
            {"error": "bad", "error_type": "invalid_dimension", "retry_count": 1}
        )
        sql = recovery_node(
            {"error": "bad", "error_type": "invalid_sql", "retry_count": 2}
        )

        self.assertEqual(route_after_recovery(dimension), "retry_metadata")
        self.assertEqual(dimension["retry_count"], 2)
        self.assertEqual(route_after_recovery(sql), "answer")
        self.assertEqual(sql["error_type"], "clarification_required")

    def test_timeout_retries_exact_validated_sql_once(self):
        state = {
            "error": "timed out",
            "error_type": "database_timeout",
            "retry_count": 0,
            "sql": "SELECT 1",
            "sql_parameters": {"filter_1": "value"},
            "sql_compilation": {"metric_id": "employee_count"},
        }

        retried = recovery_node(state)
        exhausted = recovery_node({**state, "retry_count": 1})

        self.assertEqual(route_after_recovery(retried), "retry_database")
        self.assertEqual(retried["sql"], "SELECT 1")
        self.assertEqual(retried["sql_parameters"], {"filter_1": "value"})
        self.assertIsNone(retried["error"])
        self.assertEqual(route_after_recovery(exhausted), "answer")

    def test_database_classifies_timeout_for_bounded_retry(self):
        with patch("agent.database.resolve_executor", side_effect=TimeoutError("timed out")):
            state = execute_sql({"sql": "SELECT 1"})

        self.assertEqual(state["error_type"], "database_timeout")


if __name__ == "__main__":
    unittest.main()
