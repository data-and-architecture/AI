import unittest

from agent.answer_generator import generate_answer


class AnswerGeneratorTests(unittest.TestCase):

    def _state(self, can_view_sql=False):
        return {
            "result_verification": {"valid": True},
            "query_plan": {
                "metric": "employee_count",
                "dimensions": ["department"],
                "filters": [{"column": "employees.job_title", "operator": "equals", "value": "Engineer"}],
            },
            "sql_compilation": {
                "metric_id": "employee_count",
                "base_dataset": "employees",
                "dimensions": [{"dimension_id": "department"}],
            },
            "result": [{"department": "Engineering", "employee_count": 4}],
            "policy_decision": {
                "row_filters": [
                    {
                        "dataset_id": "employees",
                        "column_id": "employment_status",
                        "operator": "!=",
                        "value": "TERMINATED",
                    }
                ]
            },
            "security_context": {"authenticated": True, "can_view_sql": can_view_sql},
            "sql": "SELECT COUNT(*) AS employee_count FROM employees",
        }

    def test_answers_only_from_verified_data_and_explains_context(self):
        answer = generate_answer(self._state())["answer"]

        self.assertIn("Employee Count", answer)
        self.assertIn("HR domain, Employees dataset", answer)
        self.assertIn("employees.job_title equals Engineer", answer)
        self.assertIn("department=Engineering: 4", answer)
        self.assertNotIn("SQL:", answer)

    def test_shows_sql_only_to_technical_users(self):
        analyst_answer = generate_answer(self._state(False))["answer"]
        technical_answer = generate_answer(self._state(True))["answer"]

        self.assertNotIn("SQL:", analyst_answer)
        self.assertIn("```sql", technical_answer)

    def test_treats_empty_results_as_a_verified_answer(self):
        state = self._state()
        state["result"] = []

        answer = generate_answer(state)["answer"]

        self.assertIn("No verified rows matched", answer)

    def test_returns_safe_targeted_clarification_for_unsafe_requests(self):
        answer = generate_answer(
            {
                "error": "internal details must not leak",
                "error_type": "invalid_plan",
                "query_understanding": {
                    "clarification_question": "Which department should I use?"
                },
            }
        )["answer"]

        self.assertIn("Which department should I use?", answer)
        self.assertNotIn("internal details", answer)


if __name__ == "__main__":
    unittest.main()
