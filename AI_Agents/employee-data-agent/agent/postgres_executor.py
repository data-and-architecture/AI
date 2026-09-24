import json
from typing import Any, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from agent.query_executor import ExecutionLimits, QueryExecutionResult, QueryExecutor


class PostgresExecutor(QueryExecutor):
    """Pooled PostgreSQL executor for a read-only service identity."""

    def __init__(self, connection_url: str, pool_size: int = 5, max_overflow: int = 5):
        if not connection_url.startswith("postgresql+psycopg://"):
            connection_url = connection_url.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        self._engine: Engine = create_engine(
            connection_url,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )

    def execute(
        self,
        sql: str,
        parameters: Mapping[str, Any],
        limits: ExecutionLimits,
    ) -> QueryExecutionResult:
        timeout_ms = int(limits.max_execution_seconds) * 1000
        if not (0 < timeout_ms <= 300_000):
            raise ValueError(f"max_execution_seconds out of range: {limits.max_execution_seconds}")
        with self._engine.begin() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
            self._check_scan_limit(connection, sql, parameters, limits.max_scan_mb)
            result = connection.execute(text(sql), parameters)
            rows = [dict(row) for row in result.mappings().fetchmany(limits.max_rows + 1)]

        if len(rows) > limits.max_rows:
            raise RuntimeError("Query result exceeds the policy row limit")
        return QueryExecutionResult(rows=rows, row_count=len(rows))

    @staticmethod
    def _check_scan_limit(connection, sql: str, parameters: Mapping[str, Any], max_scan_mb: int) -> None:
        max_scan_rows = max_scan_mb * 1024  # ~1 KB/row heuristic.
        result = connection.execute(text(f"EXPLAIN (FORMAT JSON) {sql}"), parameters)
        plan_json = result.scalar_one()
        if isinstance(plan_json, str):
            plan_json = json.loads(plan_json)
        estimated_rows = plan_json[0]["Plan"].get("Plan Rows", 0)
        if estimated_rows > max_scan_rows:
            raise RuntimeError(
                f"Estimated scan of {estimated_rows} rows exceeds the "
                f"policy limit of {max_scan_rows} rows (~{max_scan_mb} MB)"
            )
