from datetime import date, datetime
from decimal import Decimal
from numbers import Number
from typing import Any

from agent.metadata_loader import MetadataLoader
from agent.state import AgentState

metadata = MetadataLoader("metadata").load()


def _failure(state: AgentState, message: str) -> AgentState:
    return {
        **state,
        "result_verification": {"valid": False, "reason": message},
        "error": message,
        "error_type": "result_verification_error",
    }


def _column_type_is_valid(value: Any, data_type: str) -> bool:
    if value is None:
        return True
    if data_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if data_type == "decimal":
        return isinstance(value, Number) and not isinstance(value, bool)
    if data_type == "date":
        return isinstance(value, (date, datetime))
    return isinstance(value, str)


def _metric_value_is_valid(value: Any, metric_format: str) -> bool:
    if value is None:
        return True
    if metric_format in {"integer", "currency", "decimal", "percentage"}:
        return isinstance(value, Number) and not isinstance(value, bool)
    return True


def _same_numeric_value(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return abs(Decimal(str(left)) - Decimal(str(right))) <= Decimal("0.000001")


def _run_deterministic_verification(state: AgentState, metric_id: str) -> str | None:
    metric = metadata.get_metric(metric_id)
    verification = metric.get("verification", {}) if metric else {}
    if verification.get("mode") != "sum_of_groups" or not state.get("result"):
        return None

    from agent.database import resolve_executor

    executor, limits = resolve_executor(state)
    verification_sql = (
        f"SELECT SUM(verification_source.{metric_id}) AS verification_metric "
        f"FROM ({state['sql'].rstrip(';')}) AS verification_source"
    )
    verification_result = executor.execute(
        verification_sql,
        state.get("sql_parameters", {}),
        limits,
    )
    verification_value = (
        verification_result.rows[0].get("verification_metric")
        if verification_result.rows
        else None
    )
    result_value = sum(
        (
            Decimal(str(row[metric_id]))
            for row in state["result"]
            if row[metric_id] is not None
        ),
        Decimal("0"),
    )
    if not _same_numeric_value(result_value, verification_value):
        return "Deterministic verification query did not match the result metric"
    return None


def verify_result(state: AgentState) -> AgentState:
    """Verify successful execution output against the approved plan and catalog."""

    if state.get("error"):
        return _failure(state, "Database execution did not succeed")

    compilation = state.get("sql_compilation") or {}
    plan = state.get("query_plan") or {}
    metric_id = compilation.get("metric_id")
    metric = metadata.get_metric(metric_id) if metric_id else None
    if not metric or metric_id != plan.get("metric"):
        return _failure(state, "Result metric does not match the approved query plan")

    requested_dimensions = plan.get("dimensions", [])
    compiled_dimensions = compilation.get("dimensions", [])
    compiled_dimension_ids = [item.get("dimension_id") for item in compiled_dimensions]
    if compiled_dimension_ids != requested_dimensions:
        return _failure(state, "Result dimensions do not match the approved query plan")

    dimensions = []
    for dimension_id in requested_dimensions:
        dimension = metadata.get_dimension(dimension_id)
        if not dimension:
            return _failure(state, f"Requested dimension does not exist: {dimension_id}")
        source = dimension["source"]
        column = metadata.get_column(f"{source['dataset']}.{source['column']}")
        if not column:
            return _failure(state, f"Dimension source column does not exist: {dimension_id}")
        dimensions.append((dimension_id, column["data_type"]))

    result = state.get("result") or []
    if not result:
        return {
            **state,
            "result_verification": {
                "valid": True,
                "row_count": 0,
                "verification_query": "skipped_empty_result",
            },
            "error": None,
            "error_type": None,
        }

    expected_columns = {metric_id, *requested_dimensions}
    group_keys: set[tuple[Any, ...]] = set()
    for row in result:
        if set(row) != expected_columns:
            return _failure(state, "Result shape does not match requested metric and dimensions")
        if not _metric_value_is_valid(row[metric_id], metric.get("format", {}).get("type", "")):
            return _failure(state, f"Metric has an invalid result type: {metric_id}")

        group_key = tuple(row[dimension_id] for dimension_id, _ in dimensions)
        if dimensions and group_key in group_keys:
            return _failure(state, "Result contains duplicate dimension groups")
        group_keys.add(group_key)

        for dimension_id, data_type in dimensions:
            if not _column_type_is_valid(row[dimension_id], data_type):
                return _failure(state, f"Dimension has an invalid result type: {dimension_id}")

    if not dimensions and len(result) != 1:
        return _failure(state, "Ungrouped metric query returned multiple rows")

    try:
        verification_error = _run_deterministic_verification(state, metric_id)
    except Exception as exc:
        return _failure(state, f"Deterministic verification query failed: {exc}")
    if verification_error:
        return _failure(state, verification_error)

    return {
        **state,
        "result_verification": {
            "valid": True,
            "row_count": len(result),
            "verification_query": "passed" if metric.get("verification") else "not_configured",
        },
        "error": None,
        "error_type": None,
    }
