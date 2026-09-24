import hashlib
import json
import logging
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from time import perf_counter
from typing import Any, cast
from uuid import uuid4

from agent.metadata_loader import MetadataLoader
from agent.observability import record_request_outcome, record_request_started
from agent.state import AgentState

metadata = MetadataLoader("metadata").load()
logger = logging.getLogger("employee_data_agent.audit")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False
_recent_events: deque[dict[str, Any]] = deque(maxlen=200)
_recent_events_lock = Lock()


def audit_start_node(state: AgentState) -> AgentState:
    state_data = cast(dict[str, Any], state)
    request_id = state_data.get("request_id") or str(uuid4())
    correlation_id = state_data.get("correlation_id") or request_id
    started_state = {
        **state,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "audit_started_at": datetime.now(timezone.utc).isoformat(),
        "audit_started_perf": perf_counter(),
    }
    record_request_started(started_state)
    return started_state


def _answer_status(state: AgentState) -> str:
    state_data = cast(dict[str, Any], state)
    error_type = state_data.get("error_type")
    if error_type in {"policy_denied", "policy_unavailable", "authentication_error"}:
        return "denied"
    if error_type in {"ambiguous_term", "clarification_required"}:
        return "clarification_required"
    if state_data.get("error"):
        return "failed"
    if state_data.get("answer"):
        return "answered"
    return "incomplete"


def _policy_summary(policy_decision: dict[str, Any] | None) -> dict[str, Any] | None:
    if not policy_decision:
        return None
    limits = policy_decision.get("limits", {})
    return {
        "allowed": policy_decision.get("allowed", False),
        "reason": policy_decision.get("reason"),
        "row_filter_count": len(policy_decision.get("row_filters", [])),
        "masking_rule_count": len(policy_decision.get("masking_rules", [])),
        "limits": {
            "max_rows": limits.get("max_rows"),
            "max_scan_mb": limits.get("max_scan_mb"),
            "max_execution_seconds": limits.get("max_execution_seconds"),
        },
    }


def _sql_hash(sql: str | None) -> str | None:
    if not sql:
        return None
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def recent_audit_events(limit: int = 50) -> list[dict[str, Any]]:
    """Return bounded, sanitized audit events for authorized admin views."""

    with _recent_events_lock:
        return list(_recent_events)[-max(1, min(limit, 200)) :]


def audit_node(state: AgentState) -> AgentState:
    """Emit a structured audit event without query text, parameters, or result data."""

    state_data = cast(dict[str, Any], state)
    context = cast(dict[str, Any], state_data.get("security_context") or {})
    user = cast(dict[str, Any], context.get("user") or {})
    plan = cast(dict[str, Any], state_data.get("query_plan") or {})
    compilation = cast(dict[str, Any], state_data.get("sql_compilation") or {})
    dimensions = [item["dimension_id"] for item in compilation.get("dimensions", [])]
    resolved_datasets = plan.get("datasets", [])

    event: dict[str, Any] = {
        "event_type": "data_query_audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": state_data.get("request_id"),
        "correlation_id": state_data.get("correlation_id"),
        "user": {
            "user_id": user.get("user_id"),
            "username": user.get("username"),
            "roles": user.get("roles", []),
        },
        "metadata_version": getattr(metadata, "version", "unknown"),
        "resolved": {
            "metric_id": compilation.get("metric_id") or plan.get("metric"),
            "dimension_ids": dimensions or plan.get("dimensions", []),
            "dataset_ids": resolved_datasets,
        },
        "policy_decision": _policy_summary(state_data.get("policy_decision")),
        "sql_hash": _sql_hash(state_data.get("sql")),
        "execution_duration_ms": state_data.get("execution_duration_ms"),
        "row_count": len(state_data.get("result") or []),
        "error_type": state_data.get("error_type"),
        "answer_status": _answer_status(state),
        "retry_count": state_data.get("retry_count", 0),
    }
    logger.info(json.dumps(event, default=str, sort_keys=True))
    with _recent_events_lock:
        _recent_events.append(event)
    audited_state = {**state, "audit_event": event}
    record_request_outcome(audited_state)
    return audited_state
