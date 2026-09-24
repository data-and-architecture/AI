import unittest

from agent.observability import (
    REQUEST_COUNT,
    instrument_node,
    prometheus_metrics,
    record_request_outcome,
)


class ObservabilityTests(unittest.TestCase):

    def test_instrumented_node_returns_state_without_payload_metrics(self):
        wrapped = instrument_node(
            "test_observability_node",
            lambda state: {**state, "answer": "sensitive answer text"},
        )

        result = wrapped({"request_id": "request-abc", "correlation_id": "corr-abc"})
        metrics = prometheus_metrics().decode()

        self.assertEqual(result["answer"], "sensitive answer text")
        self.assertIn("employee_data_agent_node_latency_seconds", metrics)
        self.assertNotIn("sensitive answer text", metrics)
        self.assertNotIn("request-abc", metrics)

    def test_terminal_outcomes_increment_normalized_request_metrics(self):
        before = REQUEST_COUNT.labels(outcome="refusal")._value.get()
        record_request_outcome(
            {
                "audit_event": {"answer_status": "denied"},
                "error_type": "policy_denied",
                "retry_count": 0,
            }
        )

        self.assertEqual(REQUEST_COUNT.labels(outcome="refusal")._value.get(), before + 1)


if __name__ == "__main__":
    unittest.main()
