"""
Canonical filter operators shared by query-plan validation and SQL
compilation, so the set of operators a plan is validated against
can never drift from the set the compiler knows how to render.
"""

OPERATOR_SQL = {
    "equals": "=",
    "not_equals": "!=",
    "greater_than": ">",
    "greater_than_or_equal": ">=",
    "less_than": "<",
    "less_than_or_equal": "<=",
}


def to_sql_operator(operator: str) -> str:
    return OPERATOR_SQL.get(operator, "=")
