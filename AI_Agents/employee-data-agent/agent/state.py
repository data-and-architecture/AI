from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # ---------------------------------------------------------
    # User
    # ---------------------------------------------------------
    question: str
    conversation_history: list[dict[str, str]]
    cancellation_event: Any

    # ---------------------------------------------------------
    # Policy and Security Gate
    # ---------------------------------------------------------
    token: str
    security_context: dict[str, Any]
    policy_decision: dict[str, Any]

    # ---------------------------------------------------------
    # Metadata investigation (populated by the metadata agent's
    # tool-calling loop; a text digest of everything the LLM
    # discovered via search_glossary / search_metrics / etc.)
    # ---------------------------------------------------------
    metadata_context: dict[str, Any]
    glossary_terms: list[dict[str, Any]]
    metrics: list[dict[str, Any]]
    dimensions: list[dict[str, Any]]
    datasets: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    columns: list[dict[str, Any]]


    request_id: str
    correlation_id: str
    audit_started_at: str
    audit_started_perf: float

    # ---------------------------------------------------------
    # Query Understanding
    # ---------------------------------------------------------
    query_understanding: dict


    # ---------------------------------------------------------
    # Query
    # ---------------------------------------------------------
    query_plan: dict[str, Any]
    sql: str
    sql_parameters: dict[str, Any]
    sql_compilation: dict[str, Any] | None

    # ---------------------------------------------------------
    # Execution
    # ---------------------------------------------------------
    result: list[dict[str, Any]]
    result_summary: str
    result_verification: dict[str, Any]
    execution_duration_ms: float

    # ---------------------------------------------------------
    # Output
    # ---------------------------------------------------------
    answer: str
    audit_event: dict[str, Any]

    # ---------------------------------------------------------
    # Error handling / recovery
    # ---------------------------------------------------------
    error: str | None
    error_type: str | None
    retry_count: int
    recovery_action: str
