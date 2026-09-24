import json
import logging
import os
from functools import wraps
from time import perf_counter
from typing import Any, Callable, cast

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, generate_latest

from agent.state import AgentState

_service_name = "employee-data-agent"
_tracer_provider_configured = False


def configure_tracing() -> None:
    """Configure a local provider; deployments attach an OTLP exporter externally."""

    global _tracer_provider_configured
    if _tracer_provider_configured:
        return
    provider = TracerProvider(
        resource=Resource.create({"service.name": _service_name})
    )
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _tracer_provider_configured = True


configure_tracing()
tracer = trace.get_tracer(_service_name)
logger = logging.getLogger("employee_data_agent.observability")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

REQUEST_COUNT = Counter(
    "employee_data_agent_requests_total",
    "Total query requests by terminal outcome.",
    ["outcome"],
)
REQUEST_LATENCY = Histogram(
    "employee_data_agent_request_latency_seconds",
    "End-to-end request latency.",
    ["outcome"],
)
NODE_LATENCY = Histogram(
    "employee_data_agent_node_latency_seconds",
    "LangGraph node execution latency.",
    ["node", "outcome"],
)
DATABASE_TIME = Histogram(
    "employee_data_agent_database_duration_seconds",
    "Database execution duration.",
    ["outcome"],
)
RETRY_COUNT = Counter(
    "employee_data_agent_retries_total",
    "Total recovery retries by action.",
    ["action"],
)
POLICY_DENIALS = Counter(
    "employee_data_agent_policy_denials_total",
    "Policy denials.",
)
VALIDATION_ERRORS = Counter(
    "employee_data_agent_validation_errors_total",
    "Validation failures by type.",
    ["error_type"],
)


def _state_data(state: AgentState) -> dict[str, Any]:
    return cast(dict[str, Any], state)


def _structured_log(event: str, state: AgentState, **fields: Any) -> None:
    data = _state_data(state)
    logger.info(
        json.dumps(
            {
                "event": event,
                "request_id": data.get("request_id"),
                "correlation_id": data.get("correlation_id"),
                **fields,
            },
            default=str,
            sort_keys=True,
        )
    )


def instrument_node(name: str, handler: Callable[[AgentState], AgentState]):
    """Wrap one graph node with an OpenTelemetry span, metrics, and safe logs."""

    @wraps(handler)
    def wrapped(state: AgentState) -> AgentState:
        started = perf_counter()
        data = _state_data(state)
        with tracer.start_as_current_span(f"langgraph.{name}") as span:
            span.set_attribute("langgraph.node", name)
            if data.get("request_id"):
                span.set_attribute("request.id", data["request_id"])
            if data.get("correlation_id"):
                span.set_attribute("correlation.id", data["correlation_id"])
            cancellation_event = data.get("cancellation_event")
            if cancellation_event and cancellation_event.is_set():
                return {
                    **state,
                    "error": "Request cancelled",
                    "error_type": "cancelled",
                }
            _structured_log("node_started", state, node=name)
            try:
                result = handler(state)
            except Exception as exc:
                duration = perf_counter() - started
                span.record_exception(exc)
                span.set_attribute("error.type", type(exc).__name__)
                NODE_LATENCY.labels(node=name, outcome="exception").observe(duration)
                _structured_log(
                    "node_failed", state, node=name, duration_ms=round(duration * 1000, 3),
                    error_type=type(exc).__name__,
                )
                raise

            result_data = _state_data(result)
            if cancellation_event and cancellation_event.is_set():
                result = {
                    **result,
                    "error": "Request cancelled",
                    "error_type": "cancelled",
                }
                result_data = _state_data(result)
            duration = perf_counter() - started
            outcome = "error" if result_data.get("error") else "success"
            span.set_attribute("node.outcome", outcome)
            span.set_attribute("node.duration_ms", round(duration * 1000, 3))
            if result_data.get("error_type"):
                span.set_attribute("error.type", result_data["error_type"])
            NODE_LATENCY.labels(node=name, outcome=outcome).observe(duration)
            _structured_log(
                "node_completed",
                result,
                node=name,
                outcome=outcome,
                duration_ms=round(duration * 1000, 3),
                error_type=result_data.get("error_type"),
            )
            return result

    return wrapped


def record_request_started(state: AgentState) -> None:
    _structured_log("request_started", state)


def record_request_outcome(state: AgentState) -> None:
    data = _state_data(state)
    audit_event = cast(dict[str, Any], data.get("audit_event") or {})
    answer_status = audit_event.get("answer_status", "incomplete")
    outcome = {
        "answered": "success",
        "denied": "refusal",
        "clarification_required": "clarification",
    }.get(answer_status, "failure")
    REQUEST_COUNT.labels(outcome=outcome).inc()

    started = data.get("audit_started_perf")
    if isinstance(started, float):
        REQUEST_LATENCY.labels(outcome=outcome).observe(perf_counter() - started)

    database_ms = data.get("execution_duration_ms")
    if isinstance(database_ms, (int, float)):
        DATABASE_TIME.labels(outcome="error" if data.get("error") else "success").observe(
            database_ms / 1000
        )

    error_type = data.get("error_type")
    if error_type == "policy_denied":
        POLICY_DENIALS.inc()
    if error_type in {"invalid_plan", "invalid_dimension", "invalid_sql", "unknown_metric"}:
        VALIDATION_ERRORS.labels(error_type=error_type).inc()

    retry_count = data.get("retry_count", 0)
    action = data.get("recovery_action")
    if isinstance(retry_count, int) and retry_count > 0 and action:
        RETRY_COUNT.labels(action=action).inc(retry_count)

    _structured_log(
        "request_completed",
        state,
        outcome=outcome,
        error_type=error_type,
        execution_duration_ms=database_ms,
        retry_count=retry_count,
    )


def prometheus_metrics() -> bytes:
    """Return Prometheus exposition data for an HTTP metrics endpoint."""

    return generate_latest()
