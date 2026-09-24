import unittest
from decimal import Decimal
from unittest.mock import patch

from agent.query_executor import ExecutionLimits, QueryExecutionResult
from agent.result_verifier import verify_result


class FakeExecutor:

    def __init__(self, verification_value):
        self.verification_value = verification_value
        self.sql = ""

    def execute(self, sql, parameters, limits):
        self.sql = sql
        return QueryExecutionResult(
            rows=[{"verification_metric": self.verification_value}],
            row_count=1,
        )


class ResultVerifierTests(unittest.TestCase):

    def _employee_count_state(self, result):
        return {
            "query_plan": {"metric": "employee_count", "dimensions": ["department"]},
            "sql_compilation": {
                "metric_id": "employee_count",
                "dimensions": [{"dimension_id": "department"}],
            },
            "result": result,
        }

    def test_accepts_valid_shape_and_empty_results(self):
        valid = verify_result(
            self._employee_count_state(
                [{"department": "Engineering", "employee_count": 4}]
            )
        )
        empty = verify_result(self._employee_count_state([]))

        self.assertTrue(valid["result_verification"]["valid"])
        self.assertTrue(empty["result_verification"]["valid"])
        self.assertEqual(empty["result_verification"]["row_count"], 0)

    def test_rejects_invalid_metric_type_and_duplicate_groups(self):
        invalid_type = verify_result(
            self._employee_count_state(
                [{"department": "Engineering", "employee_count": "four"}]
            )
        )
        duplicate = verify_result(
            self._employee_count_state(
                [
                    {"department": "Engineering", "employee_count": 2},
                    {"department": "Engineering", "employee_count": 2},
                ]
            )
        )

        self.assertIn("invalid result type", invalid_type["error"])
        self.assertEqual(duplicate["error"], "Result contains duplicate dimension groups")

    def _salary_state(self):
        return {
            "query_plan": {
                "metric": "total_salary",
                "dimensions": ["department"],
                "datasets": ["employees", "departments"],
            },
            "sql_compilation": {
                "metric_id": "total_salary",
                "base_dataset": "employees",
                "dimensions": [{"dimension_id": "department"}],
            },
            "sql": "SELECT 100 AS total_salary",
            "sql_parameters": {},
            "result": [{"department": "Engineering", "total_salary": Decimal("100.00")}],
        }

    def test_runs_matching_deterministic_verification_query(self):
        executor = FakeExecutor(Decimal("100.00"))
        with patch("agent.database.resolve_executor", return_value=(executor, ExecutionLimits(100, 1, 1))):
            verified = verify_result(self._salary_state())

        self.assertTrue(verified["result_verification"]["valid"])
        self.assertEqual(verified["result_verification"]["verification_query"], "passed")
        self.assertIn("SUM(verification_source.total_salary)", executor.sql)

    def test_rejects_mismatched_deterministic_verification_query(self):
        executor = FakeExecutor(Decimal("99.00"))
        with patch("agent.database.resolve_executor", return_value=(executor, ExecutionLimits(100, 1, 1))):
            verified = verify_result(self._salary_state())

        self.assertEqual(
            verified["error"],
            "Deterministic verification query did not match the result metric",
        )


if __name__ == "__main__":
    unittest.main()
