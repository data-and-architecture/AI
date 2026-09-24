from typing import Any, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from agent.query_executor import ExecutionLimits, QueryExecutionResult, QueryExecutor


class SqlServerExecutor(QueryExecutor):
    """Pooled pyodbc-backed executor for a read-only SQL Server identity."""

    def __init__(self, connection_url: str, pool_size: int = 5, max_overflow: int = 5):
        if not connection_url.startswith("mssql+pyodbc://"):
            raise ValueError("SQL Server connections must use an mssql+pyodbc URL")
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
        with self._engine.connect() as connection:
            raw_connection = connection.connection.driver_connection
            raw_connection.timeout = limits.max_execution_seconds
            result = connection.execute(text(sql), parameters)
            rows = [dict(row) for row in result.mappings().fetchmany(limits.max_rows + 1)]

        if len(rows) > limits.max_rows:
            raise RuntimeError("Query result exceeds the policy row limit")
        return QueryExecutionResult(rows=rows, row_count=len(rows))
