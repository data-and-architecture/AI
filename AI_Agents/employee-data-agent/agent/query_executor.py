from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ExecutionLimits:
    max_rows: int
    max_scan_mb: int
    max_execution_seconds: int


@dataclass(frozen=True)
class QueryExecutionResult:
    rows: list[dict[str, Any]]
    row_count: int


class QueryExecutor(ABC):
    """Database-neutral interface for controlled read-only query execution."""

    @abstractmethod
    def execute(
        self,
        sql: str,
        parameters: Mapping[str, Any],
        limits: ExecutionLimits,
    ) -> QueryExecutionResult:
        """Execute one already-validated SELECT with policy-derived limits."""
