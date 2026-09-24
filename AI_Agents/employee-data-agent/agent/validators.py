"""
Two governance gates, both of which set state["error"] instead of
raising -- so the LangGraph router can send a failure to the
recovery node instead of crashing the whole graph.

1. validate_query_plan -- every id in the plan must exist in the
   governed metadata (metric/dimension/dataset/relationship), and
   every user-supplied filter must reference an approved column,
   in scope for the plan, with an approved operator.
2. validate_sql        -- the generated SQL must be a single
   read-only SELECT against approved tables only.
"""

from typing import Any, cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from agent.metadata_loader import MetadataLoader
from agent.sql_operators import OPERATOR_SQL
from agent.state import AgentState

metadata = MetadataLoader("metadata").load()

SQL_DIALECT = "postgres"
PERMITTED_FUNCTIONS = {"AVG", "CAST", "COUNT", "LEFT", "MD5", "SUM"}
DISALLOWED_EXPRESSIONS = (
    exp.Anonymous,
    exp.Between,
    exp.Case,
    exp.In,
    exp.Like,
    exp.Or,
    exp.Star,
    exp.Subquery,
    exp.Window,
)


def validate_query_plan(state: AgentState) -> AgentState:
    state_data = cast(dict[str, Any], state)
    plan = state_data.get("query_plan") or {}

    if plan.get("clarification_required"):
        return {
            **state,
            "error": "Clarification required",
            "error_type": "ambiguous_term",
        }

    metric_id = plan.get("metric")
    metric = metadata.get_metric(metric_id) if metric_id else None
    if not metric:
        return {
            **state,
            "error": f"Metric not found: {metric_id!r}",
            "error_type": "unknown_metric",
        }

    for dimension_id in plan.get("dimensions", []):
        if not metadata.get_dimension(dimension_id):
            return {
                **state,
                "error": f"Dimension not found: {dimension_id!r}",
                "error_type": "invalid_dimension",
            }

    for dataset_id in plan.get("datasets", []):
        if not metadata.get_dataset(dataset_id):
            return {
                **state,
                "error": f"Dataset not found: {dataset_id!r}",
                "error_type": "invalid_plan",
            }

    for relationship_id in plan.get("relationships", []):
        if not metadata.get_relationship(relationship_id):
            return {
                **state,
                "error": f"Relationship not found: {relationship_id!r}",
                "error_type": "invalid_plan",
            }

    # Every user-supplied filter must point at a real catalog column
    # that is actually in scope for this plan (the metric's own
    # source dataset, or one of its requested dimensions' datasets),
    # and use one of the operators the SQL compiler knows how to
    # render safely.
    in_scope_datasets = set(plan.get("datasets", []))
    in_scope_datasets.add(metric["source"]["dataset"])
    for dimension_id in plan.get("dimensions", []):
        dimension = metadata.get_dimension(dimension_id)
        if dimension:
            in_scope_datasets.add(dimension["source"]["dataset"])

    for filter_item in plan.get("filters", []):
        column_id = filter_item.get("column")
        column = metadata.get_column(column_id) if column_id else None
        if not column:
            return {
                **state,
                "error": f"Filter column not approved: {column_id!r}",
                "error_type": "invalid_plan",
            }
        if column["dataset"] not in in_scope_datasets:
            return {
                **state,
                "error": f"Filter column not in scope for this plan: {column_id!r}",
                "error_type": "invalid_plan",
            }
        operator = filter_item.get("operator")
        if operator not in OPERATOR_SQL:
            return {
                **state,
                "error": f"Filter operator not allowed: {operator!r}",
                "error_type": "invalid_plan",
            }

    return {**state, "error": None, "error_type": None}


def _invalid_sql(state: AgentState, message: str) -> AgentState:
    return {**state, "error": message, "error_type": "invalid_sql"}


def _contains_comment(sql: str) -> bool:
    """Detect comment syntax outside quoted string/identifier literals."""

    index = 0
    quote: str | None = None
    while index < len(sql):
        character = sql[index]
        if quote:
            if character == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
        elif sql[index : index + 2] in {"--", "/*", "*/"}:
            return True
        index += 1
    return False


def _normalized_expression(sql: str) -> str:
    statement = sqlglot.parse_one(f"SELECT {sql}", read=SQL_DIALECT)
    expression = statement.expressions[0]
    return expression.sql(dialect=SQL_DIALECT)


def _normalized_predicate(sql: str) -> str:
    statement = sqlglot.parse_one(f"SELECT 1 WHERE {sql}", read=SQL_DIALECT)
    return statement.args["where"].this.sql(dialect=SQL_DIALECT)


def _flatten_and(expression: Any) -> list[Any]:
    if isinstance(expression, exp.And):
        return _flatten_and(expression.left) + _flatten_and(expression.right)
    return [expression]


def _metadata_tables() -> dict[str, str]:
    return {
        dataset["database"]["table"]: dataset_id
        for dataset_id, dataset in metadata.datasets.items()
    }


def _metadata_columns() -> set[tuple[str, str]]:
    tables = _metadata_tables()
    return {
        (tables[column["dataset"]], column["name"])
        for column in metadata.columns.values()
    }


def _approved_join_predicates() -> dict[str, str]:
    predicates: dict[str, str] = {}
    for relationship_id, relationship in metadata.relationships.items():
        from_table = _metadata_tables()[relationship["from"]["dataset"]]
        to_table = _metadata_tables()[relationship["to"]["dataset"]]
        condition = (
            f"{from_table}.{relationship['from']['column']} = "
            f"{to_table}.{relationship['to']['column']}"
        )
        predicates[relationship_id] = _normalized_predicate(condition)
    return predicates


def _expected_dimension_expression(column: str, masking_strategy: str | None) -> str:
    if masking_strategy == "partial":
        return f"(left({column}::text, 2) || '***')"
    if masking_strategy == "hash":
        return f"md5({column}::text)"
    if masking_strategy:
        return "NULL"
    return column


def validate_sql(state: AgentState) -> AgentState:
    """Validate one compiler-produced PostgreSQL SELECT using sqlglot's AST."""

    state_data = cast(dict[str, Any], state)
    sql = (state_data.get("sql") or "").strip()
    compilation = state_data.get("sql_compilation")
    policy_decision = state_data.get("policy_decision") or {}

    if not sql:
        return _invalid_sql(state, "No SQL was generated")
    if not compilation:
        return _invalid_sql(state, "SQL compilation metadata is required")
    if not policy_decision.get("allowed"):
        return _invalid_sql(state, "An allowed policy decision is required")
    if _contains_comment(sql):
        return _invalid_sql(state, "SQL comments are not permitted")

    try:
        statements = sqlglot.parse(sql, read=SQL_DIALECT)
    except ParseError as exc:
        return _invalid_sql(state, f"Invalid PostgreSQL syntax: {exc}")

    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return _invalid_sql(state, "Exactly one SELECT statement is allowed")

    statement = statements[0]
    if statement.args.get("with_") or statement.args.get("into"):
        return _invalid_sql(state, "CTEs and SELECT INTO are not allowed")
    if any(statement.find(expression_type) for expression_type in DISALLOWED_EXPRESSIONS):
        return _invalid_sql(state, "SQL contains an expression that is not permitted")

    unsupported_functions = {
        function.sql_name().upper()
        for function in statement.find_all(exp.Func)
        if not isinstance(function, exp.And)
        and function.sql_name().upper() not in PERMITTED_FUNCTIONS
    }
    if unsupported_functions:
        return _invalid_sql(
            state,
            f"SQL uses functions that are not permitted: {sorted(unsupported_functions)}",
        )

    tables = _metadata_tables()
    actual_tables: list[str] = []
    for table in statement.find_all(exp.Table):
        if table.db or table.catalog or table.args.get("alias"):
            return _invalid_sql(state, "Schemas, catalogs, and table aliases are not allowed")
        if table.name not in tables:
            return _invalid_sql(state, f"Unauthorized table: {table.name}")
        actual_tables.append(table.name)

    expected_tables = compilation.get("tables") or [compilation["base_table"]]
    if "tables" not in compilation:
        for dimension in compilation.get("dimensions", []):
            table_name = dimension["column"].split(".", maxsplit=1)[0]
            if table_name not in expected_tables:
                expected_tables.append(table_name)
    if actual_tables != expected_tables:
        return _invalid_sql(state, "SQL tables do not match the compilation metadata")

    catalog_columns = _metadata_columns()
    for column in statement.find_all(exp.Column):
        if not column.table:
            return _invalid_sql(state, f"Column must be qualified: {column.name}")
        if (column.table, column.name) not in catalog_columns:
            return _invalid_sql(
                state,
                f"Unauthorized column: {column.table}.{column.name}",
            )

    from_table = statement.args["from_"].this
    if not isinstance(from_table, exp.Table) or from_table.name != compilation["base_table"]:
        return _invalid_sql(state, "SQL base table does not match the compilation metadata")

    approved_join_predicates = _approved_join_predicates()
    expected_relationships: list[str] = compilation.get("relationships", [])
    joins: list[Any] = list(statement.args.get("joins") or [])
    if len(joins) != len(expected_relationships):
        return _invalid_sql(state, "SQL joins do not match the compilation metadata")
    for join, relationship_id in zip(joins, expected_relationships):
        if (
            join.args.get("kind") not in {None, "INNER"}
            or join.args.get("side")
            or join.args.get("method")
            or not join.args.get("on")
            or relationship_id not in approved_join_predicates
        ):
            return _invalid_sql(state, "SQL contains an unauthorized join")
        actual_predicate = join.args["on"].sql(dialect=SQL_DIALECT)
        if actual_predicate != approved_join_predicates[relationship_id]:
            return _invalid_sql(state, "SQL join condition is not an approved relationship")

    metric_id = compilation["metric_id"]
    metric = metadata.get_metric(metric_id)
    if not metric:
        return _invalid_sql(state, f"Compiled metric is not approved: {metric_id}")

    masking_by_column = {
        rule["column_id"]: rule["strategy"]
        for rule in policy_decision.get("masking_rules", [])
    }
    expected_select: list[tuple[str, str]] = []
    for dimension in compilation.get("dimensions", []):
        expression = _expected_dimension_expression(
            dimension["column"],
            masking_by_column.get(dimension["column"]),
        )
        expected_select.append((dimension["dimension_id"], _normalized_expression(expression)))
    expected_select.append((metric_id, _normalized_expression(metric["expression"]["sql"])))

    actual_select: list[tuple[str, str]] = []
    for expression in statement.expressions:
        if not isinstance(expression, exp.Alias):
            return _invalid_sql(state, "Every selected expression must have an approved alias")
        actual_select.append((expression.alias, expression.this.sql(dialect=SQL_DIALECT)))
    if actual_select != expected_select:
        return _invalid_sql(state, "SQL select expressions do not match the compilation metadata")

    expected_predicates = [
        _normalized_predicate(predicate)
        for predicate in (
            compilation.get("metric_filters", [])
            + compilation.get("user_filters", [])
            + compilation.get("row_filters", [])
        )
    ]
    where = statement.args.get("where")
    actual_predicates = (
        [predicate.sql(dialect=SQL_DIALECT) for predicate in _flatten_and(where.this)]
        if where
        else []
    )
    if actual_predicates != expected_predicates:
        return _invalid_sql(state, "SQL filters do not match the compilation metadata")

    expected_group_columns = [dimension["column"] for dimension in compilation.get("dimensions", [])]
    group = statement.args.get("group")
    actual_group_columns = [
        expression.sql(dialect=SQL_DIALECT) for expression in group.expressions
    ] if group else []
    if actual_group_columns != expected_group_columns:
        return _invalid_sql(state, "SQL GROUP BY must contain only approved dimensions")

    order = statement.args.get("order")
    actual_order_columns = [
        ordered.this.sql(dialect=SQL_DIALECT) for ordered in order.expressions
    ] if order else []
    if actual_order_columns != expected_group_columns:
        return _invalid_sql(state, "SQL ORDER BY must contain only approved dimensions")

    limits = policy_decision.get("limits", {})
    policy_max_rows = limits.get("max_rows")
    compiled_limit = compilation.get("row_limit")
    limit = statement.args.get("limit")
    if not isinstance(limit, exp.Limit) or not isinstance(limit.expression, exp.Literal):
        return _invalid_sql(state, "SQL requires a literal LIMIT")
    try:
        actual_limit = int(limit.expression.this)
    except ValueError:
        return _invalid_sql(state, "SQL LIMIT must be a positive integer")
    if actual_limit <= 0 or actual_limit != compiled_limit:
        return _invalid_sql(state, "SQL LIMIT does not match the compilation metadata")
    if policy_max_rows is None or actual_limit > policy_max_rows:
        return _invalid_sql(state, "SQL LIMIT exceeds the policy result-size limit")
    max_execution_seconds = limits.get("max_execution_seconds")
    if (
        not isinstance(max_execution_seconds, int)
        or max_execution_seconds <= 0
        or compilation.get("max_execution_seconds") != max_execution_seconds
    ):
        return _invalid_sql(state, "SQL compilation timeout does not match policy")
    max_scan_mb = limits.get("max_scan_mb")
    if (
        not isinstance(max_scan_mb, int)
        or max_scan_mb <= 0
        or compilation.get("max_scan_mb") != max_scan_mb
    ):
        return _invalid_sql(state, "SQL compilation scan limit does not match policy")

    return {**state, "error": None, "error_type": None}
