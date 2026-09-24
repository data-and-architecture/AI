from agent.state import AgentState

MAX_METADATA_RETRIES = 2
MAX_DISCOVERY_RETRIES = 1
MAX_TIMEOUT_RETRIES = 1

_NO_RETRY_ERRORS = {
    "authentication_error",
    "policy_denied",
    "policy_unavailable",
    "ambiguous_term",
    "clarification_required",
}


def _answer(state: AgentState) -> AgentState:
    return {**state, "recovery_action": "answer"}


def _retry_metadata(state: AgentState, retry_count: int) -> AgentState:
    return {
        **state,
        "retry_count": retry_count,
        "recovery_action": "retry_metadata",
        "error": None,
        "error_type": None,
        "sql": "",
        "sql_parameters": {},
        "sql_compilation": None,
        "query_plan": {},
    }


def recovery_node(state: AgentState) -> AgentState:
    error_type = state.get("error_type") or "unknown_failure"
    retry_count = state.get("retry_count", 0)

    # Access/policy decisions and ambiguity are terminal: never retry
    # around a denial or attempt to guess what the user meant.
    if error_type in _NO_RETRY_ERRORS:
        return _answer(state)

    if error_type == "unknown_metric":
        if retry_count >= MAX_DISCOVERY_RETRIES:
            return {
                **state,
                "error_type": "clarification_required",
                "query_understanding": {
                    "clarification_question": (
                        "Which approved metric should I use? For example: "
                        "employee count or active employee count."
                    )
                },
                "recovery_action": "answer",
            }
        return _retry_metadata(state, retry_count + 1)

    if error_type in {"invalid_dimension", "invalid_plan", "invalid_sql", "sql_generation"}:
        if retry_count >= MAX_METADATA_RETRIES:
            return {
                **state,
                "error_type": "clarification_required",
                "query_understanding": {
                    "clarification_question": (
                        "Which approved dimension should I use? For example: "
                        "department, location, job title, or employment status."
                    )
                },
                "recovery_action": "answer",
            }
        return _retry_metadata(state, retry_count + 1)

    if error_type == "database_timeout":
        if retry_count >= MAX_TIMEOUT_RETRIES:
            return _answer(state)
        # Retry the exact validated SQL once; do not regenerate a plan
        # or relax any policy-derived limit after a timeout.
        return {
            **state,
            "retry_count": retry_count + 1,
            "recovery_action": "retry_database",
            "error": None,
            "error_type": None,
        }

    return _answer(state)
