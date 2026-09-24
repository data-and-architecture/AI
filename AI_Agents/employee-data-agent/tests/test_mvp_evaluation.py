import unittest

from agent.evaluation import MVP_EVALUATION_CASES
from agent.metadata_loader import MetadataLoader
from agent.policy_engine import PolicyEngine
from agent.result_verifier import verify_result
from agent.security_context import UserIdentity
from agent.sql_generator import generate_sql
from agent.validators import validate_query_plan, validate_sql


class MvpEvaluationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.metadata = MetadataLoader("metadata").load()
        engine = PolicyEngine()
        user = UserIdentity(
            user_id="mvp-evaluator",
            username="evaluation",
            roles=["DATA_ANALYST"],
            groups=[],
        )
        cls.security_context = engine.build_security_context(user)
        cls.engine = engine
        cls.cases = {case.name: case for case in MVP_EVALUATION_CASES}

    def _validated_compilation(self, case_name):
        case = self.cases[case_name]
        state = validate_query_plan({"query_plan": case.plan})
        self.assertIsNone(state["error"], case.question)

        decision = self.engine.evaluate(case.plan, self.security_context)
        self.assertTrue(decision.allowed, case.question)
        state = generate_sql(
            {"query_plan": case.plan, "policy_decision": decision.model_dump()}
        )
        state = validate_sql(state)
        self.assertIsNone(state["error"], case.question)
        return state, decision

    def test_approved_questions_compile_and_match_seeded_results(self):
        for case_name in {
            "simple_metric",
            "metric_dimension",
            "synonym",
            "filter",
            "multiple_filters",
            "empty_result",
        }:
            with self.subTest(case=case_name):
                case = self.cases[case_name]
                state, decision = self._validated_compilation(case_name)
                verified = verify_result(
                    {
                        **state,
                        "query_plan": case.plan,
                        "policy_decision": decision.model_dump(),
                        "result": case.expected_result,
                    }
                )
                self.assertTrue(verified["result_verification"]["valid"], case.question)
                self.assertEqual(verified["result"], case.expected_result)

    def test_synonyms_resolve_to_approved_metric_and_dimension_concepts(self):
        self.assertEqual(self.metadata.resolve_synonym("staff"), "employee")
        self.assertEqual(self.metadata.resolve_synonym("team"), "department")

    def test_filter_only_join_is_compiled_from_approved_relationship(self):
        state, _ = self._validated_compilation("filter")

        self.assertIn("JOIN departments ON employees.department_id = departments.department_id", state["sql"])
        self.assertIn("departments.location = :filter_2", state["sql"])

    def test_unsupported_question_fails_safely(self):
        case = self.cases["unsupported"]
        result = validate_query_plan({"query_plan": case.plan})

        self.assertEqual(result["error_type"], case.expected_error_type)
        self.assertFalse(result.get("sql"))

    def test_unauthorized_question_is_denied_by_policy(self):
        case = self.cases["unauthorized"]
        result = validate_query_plan({"query_plan": case.plan})
        decision = self.engine.evaluate(case.plan, self.security_context)

        self.assertIsNone(result["error"])
        self.assertEqual(decision.allowed, case.expected_policy_allowed)
        self.assertIn("Metric access denied", decision.reason)

    def test_injection_is_rejected_before_sql_generation(self):
        case = self.cases["injection"]
        result = validate_query_plan({"query_plan": case.plan})

        self.assertEqual(result["error_type"], case.expected_error_type)
        self.assertIn("Filter operator not allowed", result["error"])

    def test_ambiguous_question_requires_targeted_clarification(self):
        case = self.cases["ambiguous"]
        result = validate_query_plan({"query_plan": case.plan})

        self.assertEqual(result["error_type"], case.expected_error_type)
        self.assertEqual(case.plan["clarification_question"], "Do you mean all employees or active employees?")


if __name__ == "__main__":
    unittest.main()
