import unittest

from agent.policy_engine import PolicyEngine
from agent.security_context import UserIdentity
from agent.sql_generator import generate_sql
from agent.validators import validate_sql


class SqlValidationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        engine = PolicyEngine()
        user = UserIdentity(
            user_id="test-user",
            username="test",
            roles=["DATA_ANALYST"],
            groups=[],
        )
        cls.security_context = engine.build_security_context(user)
        cls.engine = engine

    def _compiled_state(self):
        plan = {
            "metric": "employee_count",
            "dimensions": ["department"],
            "datasets": ["employees", "departments"],
            "filters": [
                {
                    "column": "employees.job_title",
                    "operator": "equals",
                    "value": "Engineer",
                }
            ],
            "limit": 100,
        }
        decision = self.engine.evaluate(plan, self.security_context)
        self.assertTrue(decision.allowed)
        return generate_sql(
            {"query_plan": plan, "policy_decision": decision.model_dump()}
        )

    def test_accepts_compiler_output(self):
        state = self._compiled_state()

        validated = validate_sql(state)

        self.assertIsNone(validated["error"])

    def test_compiler_binds_filter_values(self):
        state = self._compiled_state()

        self.assertNotIn("Engineer", state["sql"])
        self.assertIn(":filter_1", state["sql"])
        self.assertEqual(
            state["sql_parameters"],
            {"filter_1": "Engineer", "filter_2": "TERMINATED"},
        )

    def test_rejects_multiple_statements_and_ddl(self):
        state = self._compiled_state()

        validated = validate_sql({**state, "sql": state["sql"] + " DROP TABLE employees;"})

        self.assertEqual(validated["error"], "Exactly one SELECT statement is allowed")

    def test_rejects_system_schema(self):
        state = self._compiled_state()
        sql = state["sql"].replace("FROM employees", "FROM pg_catalog.pg_tables")

        validated = validate_sql({**state, "sql": sql})

        self.assertEqual(
            validated["error"], "Schemas, catalogs, and table aliases are not allowed"
        )

    def test_rejects_unapproved_column_and_join(self):
        state = self._compiled_state()
        column_sql = state["sql"].replace("employees.employee_id", "employees.salary")
        join_sql = state["sql"].replace(
            "employees.department_id = departments.department_id",
            "employees.employee_id = departments.department_id",
        )

        column_result = validate_sql({**state, "sql": column_sql})
        join_result = validate_sql({**state, "sql": join_sql})

        self.assertEqual(
            column_result["error"], "SQL select expressions do not match the compilation metadata"
        )
        self.assertEqual(
            join_result["error"], "SQL join condition is not an approved relationship")

    def test_rejects_unsupported_function_comment_and_limit(self):
        state = self._compiled_state()
        function_sql = state["sql"].replace(
            "COUNT(DISTINCT employees.employee_id)", "RANDOM()"
        )
        comment_sql = state["sql"].replace(
            "FROM employees", "FROM /* bypass */ employees"
        )
        limit_sql = state["sql"].replace("LIMIT 100", "LIMIT 5001")

        function_result = validate_sql({**state, "sql": function_sql})
        comment_result = validate_sql({**state, "sql": comment_sql})
        limit_result = validate_sql({**state, "sql": limit_sql})

        self.assertIn("RAND", function_result["error"])
        self.assertEqual(comment_result["error"], "SQL comments are not permitted")
        self.assertEqual(
            limit_result["error"], "SQL LIMIT does not match the compilation metadata"
        )


if __name__ == "__main__":
    unittest.main()
