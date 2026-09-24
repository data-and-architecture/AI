"""
Deterministic SQL Compiler (Phase 7).

Turns a validated QueryPlan into governed SQL. The LLM never writes
SQL directly: every clause is assembled mechanically from metadata
that has already been verified to exist (metadata/plan validation),
and from user filters that have already been verified to reference
an approved, in-scope column with an approved operator (see
validate_query_plan) -- so this compiler only has to *trust and
render* what came before it, not re-derive whether it is safe.

Compilation steps, in order:
  1. Resolve the metric's source dataset/table.
  2. Resolve each approved dimension's source column, joining in
     its dataset only through an approved relationship.
  3. Compile the metric's own baked-in filters.
  4. Compile the already-validated user filters.
  5. Build GROUP BY / ORDER BY strictly from the resolved dimensions.
  6. Apply the Policy and Security Gate's row-level restrictions and
     column masking.
  7. Apply the LIMIT (tightest of the plan's request and the
     policy's ceiling) -- the execution timeout is a session-level
     control enforced by the database node, using the same
     policy-derived limits surfaced in the compilation metadata
     returned here.

Returns the compiled SQL plus a `sql_compilation` metadata record
describing exactly what was resolved and applied, for auditability.

Note: metric expressions and relationship join conditions in the
YAML are written against real table names (e.g.
"COUNT(DISTINCT employees.employee_id)",
"employees.department_id = departments.department_id"), not
aliases -- so this builder uses real table names as identifiers
throughout rather than introducing short aliases that would no
longer match those pre-written fragments.
"""

import json

from agent.metadata_loader import MetadataLoader
from agent.sql_operators import to_sql_operator
from agent.state import AgentState

metadata = MetadataLoader("metadata").load()


def _dataset_table(dataset_id: str) -> str:
    dataset = metadata.get_dataset(dataset_id)
    return dataset["database"]["table"]


def _masked_expression(column_sql: str, strategy: str) -> str:
    """Rewrite a column reference per the policy's masking strategy."""

    if strategy == "partial":
        return f"(left({column_sql}::text, 2) || '***')"
    if strategy == "hash":
        return f"md5({column_sql}::text)"
    # "redact" and any unrecognized strategy fail closed to NULL.
    return "NULL"


def _find_relationship(dataset_a: str, dataset_b: str):
    for relationship_id, relationship in metadata.relationships.items():
        pair = {relationship["from"]["dataset"], relationship["to"]["dataset"]}
        if pair == {dataset_a, dataset_b}:
            return relationship_id, relationship
    return None, None


def _sql_literal(value) -> str:
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


class _ParameterBinder:

    def __init__(self):
        self.values: dict[str, object] = {}
        self._index = 0

    def bind(self, value: object) -> str:
        self._index += 1
        name = f"filter_{self._index}"
        self.values[name] = value
        return f":{name}"


def _fail(state: AgentState, message: str) -> AgentState:
    return {
        **state,
        "sql": "",
        "sql_parameters": {},
        "sql_compilation": None,
        "error": message,
        "error_type": "sql_generation",
    }

def _find_approved_relationship(
    dataset_a: str,
    dataset_b: str,
    approved_relationship_ids: set[str],
):
    for relationship_id in approved_relationship_ids:
        relationship = metadata.relationships.get(relationship_id)

        if not relationship:
            continue

        pair = {
            relationship["from"]["dataset"],
            relationship["to"]["dataset"],
        }

        if pair == {dataset_a, dataset_b}:
            return relationship_id, relationship

    return None, None


def generate_sql(state: AgentState) -> AgentState:
    plan = state.get("query_plan") or {}
    metric_id = plan.get("metric")
    metric = metadata.get_metric(metric_id) if metric_id else None

    if not metric:
        return _fail(state, f"Unknown metric: {metric_id!r}")

    policy_decision = state.get("policy_decision") or {}

    

    approved_relationship_ids = set(plan.get("relationships", []))      

    masking_by_column = {
        rule["column_id"]: rule["strategy"]
        for rule in policy_decision.get("masking_rules", [])
    }
    policy_row_filters = policy_decision.get("row_filters", [])
    policy_limits = policy_decision.get("limits", {})
    policy_max_rows = policy_limits.get("max_rows")

    # ---- 1. resolve metric source dataset ----------------------------------
    base_dataset = metric["source"]["dataset"]
    base_table = _dataset_table(base_dataset)

    select_cols: list[str] = []
    group_by_cols: list[str] = []
    joins: list[str] = []
    joined_datasets = {base_dataset}
    resolved_tables = [base_table]
    resolved_dimensions: list[dict] = []
    resolved_relationships: list[str] = []

    def join_dataset(dataset_id: str):
        if dataset_id in joined_datasets:
            return None
        #relationship_id, relationship = _find_relationship(base_dataset, dataset_id)
        relationship_id, relationship = _find_approved_relationship(
        base_dataset,
        dataset_id,
        approved_relationship_ids,
        )
        if not relationship:
            return _fail(
                state,
                f"No approved relationship between "
                f"{base_dataset!r} and {dataset_id!r}",
            )
        dataset_table = _dataset_table(dataset_id)
        joins.append(f"JOIN {dataset_table} ON {relationship['join']['condition'].strip()}")
        joined_datasets.add(dataset_id)
        resolved_tables.append(dataset_table)
        resolved_relationships.append(relationship_id)
        return None

    # ---- 2. resolve approved dimension columns + approved relationships ----
    for dimension_id in plan.get("dimensions", []):
        dimension = metadata.get_dimension(dimension_id)
        if not dimension:
            return _fail(state, f"Unknown dimension: {dimension_id!r}")
        if dimension_id not in metric.get("allowed_dimensions", []):
            return _fail(
                state,
                f"Dimension {dimension_id!r} is not an approved "
                f"dimension for metric {metric_id!r}",
            )

        dim_dataset = dimension["source"]["dataset"]
        dim_col = dimension["source"]["column"]

        join_failure = join_dataset(dim_dataset)
        if join_failure:
            return join_failure

        column_id = f"{dim_dataset}.{dim_col}"
        masking_strategy = masking_by_column.get(column_id)
        select_expression = (
            _masked_expression(column_id, masking_strategy)
            if masking_strategy
            else column_id
        )

        select_cols.append(f"{select_expression} AS {dimension_id}")
        group_by_cols.append(column_id)
        resolved_dimensions.append(
            {
                "dimension_id": dimension_id,
                "column": column_id,
                "masked": masking_strategy is not None,
            }
        )

    metric_sql = metric["expression"]["sql"]
    select_cols.append(f"{metric_sql} AS {metric_id}")

    where_clauses: list[str] = []
    compiled_metric_filters: list[str] = []
    compiled_user_filters: list[str] = []
    compiled_row_filters: list[str] = []
    parameters = _ParameterBinder()

    # ---- 3. compile approved metric filters ---------------------------------
    for metric_filter in metric.get("filters", []):
        # field is already a fully-qualified "table.column" reference.
        field = metric_filter["field"]
        join_failure = join_dataset(field.split(".", maxsplit=1)[0])
        if join_failure:
            return join_failure
        clause = (
            f"{field} "
            f"{to_sql_operator(metric_filter['operator'])} "
            f"{parameters.bind(metric_filter['value'])}"
        )
        where_clauses.append(clause)
        compiled_metric_filters.append(clause)

    # ---- 4. compile only validated user filters -----------------------------
    # validate_query_plan has already rejected any filter whose column
    # is not an approved, in-scope catalog column, or whose operator
    # is not one of the operators this compiler knows how to render --
    # this step only has to trust and render, never re-derive safety.
    for plan_filter in plan.get("filters", []):
        column = plan_filter["column"]
        join_failure = join_dataset(column.split(".", maxsplit=1)[0])
        if join_failure:
            return join_failure
        clause = (
            f"{column} {to_sql_operator(plan_filter['operator'])} "
            f"{parameters.bind(plan_filter['value'])}"
        )
        where_clauses.append(clause)
        compiled_user_filters.append(clause)

    # ---- 6. policy-derived row-level restrictions ----------------------------
    for row_filter in policy_row_filters:
        join_failure = join_dataset(row_filter["dataset_id"])
        if join_failure:
            return join_failure
        clause = (
            f"{row_filter['dataset_id']}.{row_filter['column_id']} "
            f"{row_filter['operator']} "
            f"{parameters.bind(row_filter['value'])}"
        )
        where_clauses.append(clause)
        compiled_row_filters.append(clause)

    sql_lines = [
        "SELECT",
        "    " + ",\n    ".join(select_cols),
        f"FROM {base_table}",
    ]
    sql_lines.extend(joins)
    if where_clauses:
        sql_lines.append("WHERE " + " AND ".join(where_clauses))
    if group_by_cols:
        sql_lines.append("GROUP BY " + ", ".join(group_by_cols))
        sql_lines.append("ORDER BY " + ", ".join(group_by_cols))

    # ---- 7. LIMIT + timeout controls -------------------------------------------
    # The tighter of the plan's own requested limit and the policy's
    # ceiling for this user always wins. The execution timeout itself
    # is applied by the database node from the same policy limits.
    row_limit = plan.get("limit")
    if policy_max_rows is not None:
        row_limit = min(row_limit, policy_max_rows) if row_limit else policy_max_rows
    if row_limit:
        sql_lines.append(f"LIMIT {int(row_limit)}")

    sql = "\n".join(sql_lines) + ";"

    masked_dimension_columns = {
        dimension["column"] for dimension in resolved_dimensions if dimension["masked"]
    }

    compilation = {
        "metric_id": metric_id,
        "base_dataset": base_dataset,
        "base_table": base_table,
        "tables": resolved_tables,
        "dimensions": resolved_dimensions,
        "relationships": resolved_relationships,
        "metric_filters": compiled_metric_filters,
        "user_filters": compiled_user_filters,
        "row_filters": compiled_row_filters,
        "masked_columns": sorted(masked_dimension_columns),
        "parameter_names": sorted(parameters.values),
        "row_limit": row_limit,
        "max_execution_seconds": policy_limits.get("max_execution_seconds"),
        "max_scan_mb": policy_limits.get("max_scan_mb"),
    }

    #print("Generated SQL:\n", sql)

    return {
        **state,
        "sql": sql,
        "sql_parameters": parameters.values,
        "sql_compilation": compilation,
        "error": None,
        "error_type": None,
    }
