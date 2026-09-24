from datetime import date, datetime
from decimal import Decimal
from typing import Any

from agent.metadata_loader import MetadataLoader
from agent.security_context import SecurityContext
from agent.state import AgentState

metadata = MetadataLoader("metadata").load()
MAX_DISPLAY_ROWS = 100


def _display_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _clarification(state: AgentState) -> str:
    plan = state.get("query_plan") or {}
    if plan.get("clarification_question"):
        return plan["clarification_question"]
    understanding = state.get("query_understanding") or {}
    question = understanding.get("clarification_question")
    if question:
        return question
    return (
        "Please specify an approved metric and, if needed, the dimension "
        "to group by. For example: employee count by department."
    )


def _limitation_answer(state: AgentState) -> str:
    if (state.get("query_plan") or {}).get("clarification_required"):
        return _clarification(state)

    error_type = state.get("error_type")
    if error_type in {"ambiguous_term", "clarification_required"}:
        return _clarification(state)
    if error_type == "cancelled":
        return "The request was cancelled before a verified answer was available."
    if error_type in {"policy_denied", "authentication_error", "policy_unavailable"}:
        return (
            "I can't provide that result with your current access. "
            "Please ask for an authorized metric or contact the data owner."
        )
    if error_type in {"invalid_plan", "invalid_sql", "sql_generation"}:
        return (
            "I couldn't safely resolve that request using the approved data model. "
            + _clarification(state)
        )
    if error_type in {"database_error", "result_verification_error"}:
        return (
            "I couldn't verify a safe result for that request. "
            + _clarification(state)
        )
    return "I couldn't safely answer that request. " + _clarification(state)


def _filter_descriptions(state: AgentState, metric: dict[str, Any]) -> list[str]:
    descriptions = []
    for item in metric.get("filters", []):
        descriptions.append(f"{item['field']} {item['operator']} {_display_value(item['value'])}")
    for item in (state.get("query_plan") or {}).get("filters", []):
        descriptions.append(
            f"{item['column']} {item['operator']} {_display_value(item['value'])}"
        )
    for item in (state.get("policy_decision") or {}).get("row_filters", []):
        descriptions.append(
            f"{item['dataset_id']}.{item['column_id']} "
            f"{item['operator']} {_display_value(item['value'])}"
        )
    return descriptions


def _result_lines(
    result: list[dict[str, Any]], metric_id: str, dimensions: list[str]
) -> list[str]:
    lines = []
    for row in result[:MAX_DISPLAY_ROWS]:
        if dimensions:
            group = ", ".join(
                f"{dimension}={_display_value(row[dimension])}"
                for dimension in dimensions
            )
            lines.append(f"- {group}: {_display_value(row[metric_id])}")
        else:
            lines.append(f"- {_display_value(row[metric_id])}")
    return lines


def _can_view_sql(state: AgentState) -> bool:
    context_data = state.get("security_context")
    if not context_data:
        return False
    return SecurityContext.model_validate(context_data).can_view_sql


def generate_answer(state: AgentState) -> AgentState:
    """Create a deterministic response from result-verified data only."""

    verification = state.get("result_verification") or {}
    if state.get("error") or not verification.get("valid"):
        return {**state, "answer": _limitation_answer(state)}

    compilation = state.get("sql_compilation") or {}
    metric_id = compilation.get("metric_id")
    metric = metadata.get_metric(metric_id) if metric_id else None
    if not metric:
        return {**state, "answer": _limitation_answer(state)}

    base_dataset = metadata.get_dataset(compilation.get("base_dataset"))
    if not base_dataset:
        return {**state, "answer": _limitation_answer(state)}

    dimensions = [item["dimension_id"] for item in compilation.get("dimensions", [])]
    result = state.get("result") or []
    sections = [
        f"{metric['name']}: {metric['description'].strip()}",
        f"Source: {base_dataset['domain']} domain, {base_dataset['name']} dataset.",
    ]

    filters = _filter_descriptions(state, metric)
    if filters:
        sections.append("Filters: " + "; ".join(filters) + ".")

    if not result:
        sections.append("No verified rows matched the approved request.")
    else:
        sections.append(
            "Verified result:\n" + "\n".join(_result_lines(result, metric_id, dimensions))
        )
        if len(result) > MAX_DISPLAY_ROWS:
            sections.append(
                f"Showing the first {MAX_DISPLAY_ROWS} of {len(result)} verified rows. "
                "Please narrow the dimension or add a filter for a smaller result."
            )

    if _can_view_sql(state) and state.get("sql"):
        sections.append("SQL:\n```sql\n" + state["sql"] + "\n```")

    return {**state, "answer": "\n\n".join(sections)}
