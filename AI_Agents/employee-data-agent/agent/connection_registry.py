import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from agent.postgres_executor import PostgresExecutor
from agent.query_executor import QueryExecutor
from agent.sql_server_executor import SqlServerExecutor


@dataclass(frozen=True)
class ConnectionDefinition:
    connection_id: str
    dialect: str
    database_name: str
    url_env: str
    read_only: bool
    pool_size: int
    max_overflow: int


class ConnectionRegistry:
    """Allowlisted database connections selected by catalog connection IDs."""

    def __init__(self, path: str = "config/connections.yaml"):
        self._path = Path(path)
        self._definitions: dict[str, ConnectionDefinition] = {}
        self._executors: dict[str, QueryExecutor] = {}

    @staticmethod
    def _required_string(item: dict[str, Any], field: str) -> str:
        value = item.get(field)
        if not isinstance(value, str):
            raise ValueError(f"Connection registry entry is missing string {field!r}")
        return value

    def load(self) -> "ConnectionRegistry":
        if not self._path.exists():
            raise FileNotFoundError(f"Connection registry not found: {self._path}")

        with self._path.open("r", encoding="utf-8") as file:
            raw_data: Any = yaml.safe_load(file) or {}

        if not isinstance(raw_data, dict):
            raise ValueError("Connection registry root must be a mapping")
        data = cast(dict[str, Any], raw_data)
        connections_value = data.get("connections", [])
        if not isinstance(connections_value, list):
            raise ValueError("Connection registry connections must be a list")
        connections = cast(list[Any], connections_value)

        for raw_item in connections:
            if not isinstance(raw_item, dict):
                raise ValueError("Each connection registry entry must be a mapping")
            item = cast(dict[str, Any], raw_item)
            connection_id = self._required_string(item, "id")
            dialect = self._required_string(item, "dialect")
            database_name = self._required_string(item, "database_name")
            url_env = self._required_string(item, "url_env")
            read_only = item.get("read_only", False)
            pool_size = item.get("pool_size", 5)
            max_overflow = item.get("max_overflow", 5)
            if (
                not isinstance(read_only, bool)
                or not isinstance(pool_size, int)
                or not isinstance(max_overflow, int)
            ):
                raise ValueError("Connection registry entry has invalid option types")
            definition = ConnectionDefinition(
                connection_id=connection_id,
                dialect=dialect,
                database_name=database_name,
                url_env=url_env,
                read_only=read_only,
                pool_size=pool_size,
                max_overflow=max_overflow,
            )
            if not definition.read_only:
                raise ValueError(
                    f"Connection {definition.connection_id!r} must use a read-only identity"
                )
            if definition.dialect not in {"postgres", "sqlserver"}:
                raise ValueError(f"Unsupported database dialect: {definition.dialect}")
            self._definitions[definition.connection_id] = definition
        return self

    def executor_for(self, connection_id: str, database_name: str) -> QueryExecutor:
        definition = self._definitions.get(connection_id)
        if not definition:
            raise PermissionError(f"Connection is not registered: {connection_id}")
        if definition.database_name != database_name:
            raise PermissionError("Catalog database does not match its registered connection")

        executor = self._executors.get(connection_id)
        if executor:
            return executor

        connection_url = os.getenv(definition.url_env)
        #print(f"Resolved connection URL for {connection_id}: {connection_url}")
        if not connection_url:
            raise RuntimeError(
                f"Read-only connection URL is not configured: {definition.url_env}"
            )

        if definition.dialect == "postgres":
            executor = PostgresExecutor(
                connection_url,
                pool_size=definition.pool_size,
                max_overflow=definition.max_overflow,
            )
        else:
            executor = SqlServerExecutor(
                connection_url,
                pool_size=definition.pool_size,
                max_overflow=definition.max_overflow,
            )
        self._executors[connection_id] = executor
        return executor
